"""Synthetic endgame diagnostic: Acemi self-play from standard material.

Positions are generated randomly, labelled by full-strength Stockfish (fixed
depth; not Syzygy), then Acemi plays both sides at a fixed move time. The CSV
answers "does Acemi convert basic endgames?" for KQK, KRK, KBBK, KBNK, KPK and
KRP KR-like positions.

    python -m tools.synthetic_endgames --stockfish /path/to/stockfish \
        --out data/analysis/synthetic_endgames.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ("KQK", "KRK", "KBBK", "KBNK", "KPK", "KRPKR")
ORACLE_DEPTH = {"KQK": 12, "KRK": 12, "KBBK": 12, "KBNK": 12, "KPK": 20, "KRPKR": 22}


def _empty_board() -> chess.Board:
    return chess.Board(None)  # type: ignore[arg-type]


def _place_kings(board: chess.Board, rng: random.Random) -> bool:
    for _ in range(200):
        white = rng.randrange(64)
        black = rng.randrange(64)
        if white == black or chess.square_distance(white, black) <= 1:
            continue
        board.set_piece_at(white, chess.Piece(chess.KING, chess.WHITE))
        board.set_piece_at(black, chess.Piece(chess.KING, chess.BLACK))
        board.turn = chess.WHITE
        return True
    return False


def _random_put(board: chess.Board, piece_type: int, color: bool, rng: random.Random, count: int = 1) -> bool:
    for _ in range(300):
        empty = [square for square in chess.SQUARES if board.piece_at(square) is None]
        if len(empty) < count:
            return False
        squares = rng.sample(empty, count)
        if piece_type == chess.PAWN and any(chess.square_rank(square) in (0, 7) for square in squares):
            continue
        if piece_type == chess.BISHOP and count == 2:
            colors = {chess.square_color(square) for square in squares}
            if len(colors) != 2:
                continue
        for square in squares:
            board.set_piece_at(square, chess.Piece(piece_type, color))
        return True
    return False


def generate(category: str, rng: random.Random) -> chess.Board | None:
    board = _empty_board()
    if not _place_kings(board, rng):
        return None
    white, black = chess.WHITE, chess.BLACK
    if category == "KQK":
        ok = _random_put(board, chess.QUEEN, white, rng)
    elif category == "KRK":
        ok = _random_put(board, chess.ROOK, white, rng)
    elif category == "KBBK":
        ok = _random_put(board, chess.BISHOP, white, rng, 2)
    elif category == "KBNK":
        ok = _random_put(board, chess.BISHOP, white, rng) and _random_put(board, chess.KNIGHT, white, rng)
    elif category == "KPK":
        ok = _random_put(board, chess.PAWN, white, rng)
    elif category == "KRPKR":
        ok = (
            _random_put(board, chess.ROOK, white, rng)
            and _random_put(board, chess.PAWN, white, rng)
            and _random_put(board, chess.ROOK, black, rng)
        )
    else:
        return None
    if not ok or not board.is_valid() or board.is_game_over():
        return None
    return board


def oracle_expected(board: chess.Board, engine, depth: int) -> str | None:
    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    score = info.get("score")
    if score is None:
        return None
    white = score.pov(chess.WHITE)
    if white.is_mate():
        return "win" if white.mate() > 0 else "loss"
    value = white.score()
    if value >= 200:
        return "win"
    if value <= -200:
        return "loss"
    if abs(value) <= 50:
        return "draw"
    return None


def play_selfgame(board: chess.Board, engine, movetime_ms: int, max_plies: int) -> tuple[str, int, str]:
    plies = 0
    while plies < max_plies and not board.is_game_over():
        result = engine.play(board, chess.engine.Limit(time=movetime_ms / 1000.0))
        if result.move is None:
            break
        board.push(result.move)
        plies += 1
    if board.is_checkmate():
        return ("win" if board.turn == chess.BLACK else "loss"), plies, "checkmate"
    if board.is_stalemate():
        return "draw", plies, "stalemate"
    if board.is_insufficient_material():
        return "draw", plies, "insufficient_material"
    if board.is_fifty_moves():
        return "draw", plies, "fifty_moves"
    if board.is_repetition(3):
        return "draw", plies, "threefold_repetition"
    return "draw", plies, "max_plies"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic endgame self-play diagnostic.")
    parser.add_argument("--stockfish", required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "analysis" / "synthetic_endgames.csv")
    parser.add_argument("--categories", default=",".join(CATEGORIES))
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--movetime-ms", type=int, default=500)
    parser.add_argument("--max-plies", type=int, default=80)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    stockfish = chess.engine.SimpleEngine.popen_uci(args.stockfish)
    stockfish.configure({"Threads": 1, "Hash": 64})
    acemi = chess.engine.SimpleEngine.popen_uci([sys.executable, "-m", "engine"], cwd=str(ROOT))
    rows = []
    try:
        for category in [item.strip() for item in args.categories.split(",") if item.strip()]:
            kept = 0
            attempts = 0
            while kept < args.count and attempts < args.count * 50:
                attempts += 1
                board = generate(category, rng)
                if board is None:
                    continue
                expected = oracle_expected(board, stockfish, ORACLE_DEPTH[category])
                if expected is None:
                    continue
                if category in ("KQK", "KRK", "KBBK", "KBNK") and expected != "win":
                    continue
                game = board.copy()
                result, plies, termination = play_selfgame(game, acemi, args.movetime_ms, args.max_plies)
                rows.append(
                    {
                        "category": category,
                        "fen": board.fen(),
                        "expected": expected,
                        "result": result,
                        "success": result == expected,
                        "plies": plies,
                        "termination": termination,
                        "oracle_depth": ORACLE_DEPTH[category],
                    }
                )
                kept += 1
                print(f"{category} {kept}/{args.count}: expected={expected} result={result} plies={plies} {termination}")
            if kept == 0:
                print(f"{category}: no clear positions found")
    finally:
        stockfish.quit()
        acemi.quit()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["category", "fen", "expected", "result", "success", "plies", "termination", "oracle_depth"]
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
