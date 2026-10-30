"""Texel-style tuning of the classical PSTs against recorded game results.

The engine evaluation is linear in the piece-square values, so each recorded
position becomes one row of features: for every piece type and square,
``+1`` for a White piece and ``-1`` for the mirrored Black piece, tapered by the
game phase. Material is kept fixed; only the PSTs are tuned. The target is the
observed score (win 1, draw 0.5, loss 0) from the side to move's point of view.

    python -m tools.tune --positions data/positions --out data/tune/pst.json

Tools-only dependency: numpy. The engine package stays standard-library only.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path

import numpy as np

from engine.board import BISHOP, KING, KNIGHT, PAWN, QUEEN, ROOK
from engine.eval.classic import MATERIAL, MAX_PHASE, PHASE_WEIGHT, _EG_TABLE, _MG_TABLE

PST_PIECES = (PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING)
PIECE_INDEX = {piece: index for index, piece in enumerate(PST_PIECES)}
PIECE_CHARS = {"p": PAWN, "n": KNIGHT, "b": BISHOP, "r": ROOK, "q": QUEEN, "k": KING}
SQUARES_PER_PIECE = 64
PST_PARAMETERS = len(PST_PIECES) * SQUARES_PER_PIECE * 2  # middlegame + endgame
# The engine's centipawn scale is not calibrated to game outcomes; K=100 fits the
# recorded positions far better than the usual 400 (see validation log-loss).
LOGISTIC_K = 100.0
SCORE_SCALE = math.log(10.0) / LOGISTIC_K
# Positions far outside this range are already decided; their outcome noise would
# dominate the loss and the gradient, so they are clipped out of the fit.
SCORE_LIMIT = 1200.0


def _table_parameter(table: dict[int, tuple[int, ...]], piece: int) -> list[int]:
    return list(table[piece])


def initial_parameters() -> np.ndarray:
    """Current PSTs flattened into the tuning parameter order (MG block, then EG)."""
    mg: list[int] = []
    eg: list[int] = []
    for piece in PST_PIECES:
        mg.extend(_table_parameter(_MG_TABLE, piece))
        eg.extend(_table_parameter(_EG_TABLE, piece))
    return np.asarray(mg + eg, dtype=np.float64)


def position_terms(fen: str) -> tuple[int, np.ndarray]:
    """Material and tapered PST features, from the side to move's point of view."""
    placement = fen.split()[0]
    counts = np.zeros(len(PST_PIECES) * SQUARES_PER_PIECE, dtype=np.float64)
    material = 0
    phase = 0
    for row, rank in enumerate(placement.split("/")):
        file = 0
        for char in rank:
            if char.isdigit():
                file += int(char)
                continue
            piece = PIECE_CHARS[char.lower()]
            sign = 1.0 if char.isupper() else -1.0
            material += sign * MATERIAL[piece]
            phase += PHASE_WEIGHT[piece]
            mirror_row = row if sign > 0 else 7 - row
            index = PIECE_INDEX[piece] * SQUARES_PER_PIECE + mirror_row * 8 + file
            counts[index] += sign
            file += 1
    phase = min(phase, MAX_PHASE)
    features = np.empty(PST_PARAMETERS, dtype=np.float64)
    features[: len(counts)] = counts * (phase / MAX_PHASE)
    features[len(counts) :] = counts * ((MAX_PHASE - phase) / MAX_PHASE)
    if fen.split()[1] == "b":
        material = -material
        features = -features
    return material, features


def loss_and_gradient(
    features: np.ndarray,
    material: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
    params: np.ndarray,
    l2: float,
    initial: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Weighted logistic loss of the observed scores and its gradient."""
    scores = material + features @ params
    raw = scores * SCORE_SCALE
    keep = np.abs(raw) <= SCORE_LIMIT * SCORE_SCALE
    z = np.clip(raw, -SCORE_LIMIT * SCORE_SCALE, SCORE_LIMIT * SCORE_SCALE)
    probabilities = 1.0 / (1.0 + np.exp(-z))
    epsilon = 1e-12
    log_likelihood = target * np.log(probabilities + epsilon) + (1.0 - target) * np.log(
        1.0 - probabilities + epsilon
    )
    total_weight = weights.sum()
    loss = float(-(weights @ log_likelihood) / total_weight)
    loss += l2 * float(((params - initial) ** 2).sum())
    gradient = features.T @ (weights * keep * (probabilities - target) * SCORE_SCALE) / total_weight
    gradient += 2.0 * l2 * (params - initial)
    return loss, gradient


def load_dataset(
    directory: Path, *, max_positions: int | None = None, val_modulus: int = 10
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Read position shards and split them into train/validation by Zobrist hash."""
    train = {"features": [], "material": [], "target": [], "weight": []}
    validation = {"features": [], "material": [], "target": [], "weight": []}
    seen = 0
    for path in sorted(directory.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                if record.get("is_demo"):
                    continue
                results = record.get("results") or {}
                games = results.get("wins", 0) + results.get("draws", 0) + results.get("losses", 0)
                occurrences = record.get("occurrences", 0)
                if games <= 0 or occurrences <= 0:
                    continue
                material, features = position_terms(record["fen"])
                target = (results.get("wins", 0) + 0.5 * results.get("draws", 0)) / games
                bucket = validation if int(record["zobrist_hash"], 16) % val_modulus == 0 else train
                bucket["features"].append(features.astype(np.float32))
                bucket["material"].append(material)
                bucket["target"].append(target)
                bucket["weight"].append(min(occurrences, 5))
                seen += 1
                if max_positions is not None and seen >= max_positions:
                    break
        if max_positions is not None and seen >= max_positions:
            break
    return (
        {key: np.asarray(value) for key, value in train.items()},
        {key: np.asarray(value) for key, value in validation.items()},
    )


def fit(
    train: dict[str, np.ndarray],
    validation: dict[str, np.ndarray],
    *,
    epochs: int = 150,
    learning_rate: float = 0.5,
    l2: float = 1e-4,
    beta1: float = 0.9,
    beta2: float = 0.999,
    report_every: int = 10,
) -> tuple[np.ndarray, list[dict[str, float]]]:
    """Adam on the weighted logistic loss; keep the parameters with the best validation loss."""
    initial = initial_parameters()
    params = initial.copy()
    first = np.zeros_like(params)
    second = np.zeros_like(params)
    best_params = params.copy()
    best_value = math.inf
    history: list[dict[str, float]] = []
    for epoch in range(1, epochs + 1):
        _, gradient = loss_and_gradient(
            train["features"],
            train["material"],
            train["target"],
            train["weight"],
            params,
            l2,
            initial,
        )
        first = beta1 * first + (1 - beta1) * gradient
        second = beta2 * second + (1 - beta2) * gradient * gradient
        step = learning_rate * (first / (1 - beta1**epoch)) / (np.sqrt(second / (1 - beta2**epoch)) + 1e-8)
        params = params - step
        if epoch % report_every == 0 or epoch == epochs:
            train_loss, _ = loss_and_gradient(
                train["features"], train["material"], train["target"], train["weight"], params, l2, initial
            )
            val_loss, _ = loss_and_gradient(
                validation["features"],
                validation["material"],
                validation["target"],
                validation["weight"],
                params,
                l2,
                initial,
            )
            history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
            if val_loss < best_value:
                best_value = val_loss
                best_params = params.copy()
            print(f"epoch {epoch:4d}  train {train_loss:.5f}  val {val_loss:.5f}")
    return best_params, history


def validation_report(dataset: dict[str, np.ndarray], params: np.ndarray) -> dict[str, float]:
    scores = dataset["material"] + dataset["features"] @ params
    clipped = np.clip(scores * SCORE_SCALE, -SCORE_LIMIT * SCORE_SCALE, SCORE_LIMIT * SCORE_SCALE)
    probabilities = 1.0 / (1.0 + np.exp(-clipped))
    weights = dataset["weight"]
    target = dataset["target"]
    log_loss = float(
        -(weights @ (target * np.log(probabilities + 1e-12) + (1 - target) * np.log(1 - probabilities + 1e-12)))
        / weights.sum()
    )
    predicted = (scores > 0).astype(np.float64)
    observed = (target > 0.5).astype(np.float64)
    accuracy = float((weights @ (predicted == observed)) / weights.sum())
    return {"log_loss": log_loss, "accuracy": accuracy, "positions": int(len(scores))}


def parameters_to_tables(params: np.ndarray) -> tuple[dict[int, tuple[int, ...]], dict[int, tuple[int, ...]]]:
    """Expand the tuned parameters into 64-value PSTs."""
    half = len(PST_PIECES) * SQUARES_PER_PIECE
    mg_tables: dict[int, tuple[int, ...]] = {}
    eg_tables: dict[int, tuple[int, ...]] = {}
    for piece_index, piece in enumerate(PST_PIECES):
        start = piece_index * SQUARES_PER_PIECE
        mg: list[int] = []
        eg: list[int] = []
        for square in range(64):
            value_index = start + square
            mg.append(int(round(params[value_index])))
            eg.append(int(round(params[half + value_index])))
        mg_tables[piece] = tuple(mg)
        eg_tables[piece] = tuple(eg)
    return mg_tables, eg_tables


def emit_module(path: Path, params: np.ndarray) -> None:
    """Write the tuned PSTs as an engine-independent Python module."""
    mg_tables, eg_tables = parameters_to_tables(params)
    names = {PAWN: "PAWN", KNIGHT: "KNIGHT", BISHOP: "BISHOP", ROOK: "ROOK", QUEEN: "QUEEN", KING: "KING"}
    lines = [
        '"""Generated by tools/tune.py: PSTs tuned on recorded game results."""',
        "",
        "PST_MG = {",
    ]
    for piece in PST_PIECES:
        values = ", ".join(str(value) for value in mg_tables[piece])
        lines.append(f"    {names[piece]}: ({values}),")
    lines.append("}")
    lines.append("")
    lines.append("PST_EG = {")
    for piece in PST_PIECES:
        values = ", ".join(str(value) for value in eg_tables[piece])
        lines.append(f"    {names[piece]}: ({values}),")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tune the classical PSTs on recorded positions.")
    parser.add_argument("--positions", type=Path, default=Path("data/positions"))
    parser.add_argument("--out", type=Path, default=Path("data/tune/pst.json"))
    parser.add_argument("--module", type=Path, default=None, help="write the tuned PSTs as a Python module")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--learning-rate", type=float, default=0.5)
    parser.add_argument("--l2", type=float, default=1e-4)
    parser.add_argument("--max-positions", type=int, default=None)
    parser.add_argument("--val-modulus", type=int, default=10)
    args = parser.parse_args(argv)

    train, validation = load_dataset(
        args.positions, max_positions=args.max_positions, val_modulus=args.val_modulus
    )
    print(f"train positions: {len(train['features'])}, validation: {len(validation['features'])}")
    initial = initial_parameters()
    print("baseline validation:", validation_report(validation, initial))
    params, history = fit(
        train,
        validation,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        l2=args.l2,
    )
    report = validation_report(validation, params)
    print("tuned validation:", report)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "parameters": params.tolist(),
                "initial": initial.tolist(),
                "validation": report,
                "history": history,
                "config": {
                    "epochs": args.epochs,
                    "learning_rate": args.learning_rate,
                    "l2": args.l2,
                    "val_modulus": args.val_modulus,
                    "max_positions": args.max_positions,
                },
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    if args.module is not None:
        args.module.parent.mkdir(parents=True, exist_ok=True)
        emit_module(args.module, params)
        print(f"wrote {args.module}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
