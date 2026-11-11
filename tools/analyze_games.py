"""One-off analysis of recorded Acemi games with Stockfish.

Run types are kept apart: ``AB`` (Acemi vs Acemi, usually a feature switch) and
``SF`` (Acemi vs Stockfish). Demo and AcemiRandom games are ignored.

The tool is resumable. Every game is evaluated once and written to a scratch
cache (``data/analysis/cache/``, never committed). When a chunk finishes, the
cached games are sealed into an immutable *part*: three files under
``data/analysis/parts/`` (positions, games, blunders) named by the hash of the
sorted game ids they hold, plus an entry in ``parts.json`` (game ids, row counts,
SHA-256 of each file). A part is written to a temporary file and renamed, the
manifest last, so a dead session leaves either a complete part or none. On
resume the manifest and the files are verified; a missing or damaged part is
dropped and its games are analysed again. Sealed parts are never rewritten.

    python -m tools.analyze_games --depth 10 --workers 3 --max-new-games 250
    python -m tools.analyze_games --aggregate-only      # rebuild games.csv / blunders.csv
    python -m tools.analyze_games --recheck             # depth-4 recheck of sampled blunders

``--syzygy DIR`` labels positions with 5 pieces or fewer from Syzygy WDL tables
(win/loss only for 2/-2; cursed win and blessed loss count as draws). WDL ignores
DTZ, so a labelled win is an upper bound on what is convertible in practice.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import multiprocessing as mp
import os
import random
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import chess.syzygy as chess_syzygy

from tools.analysis_config import active_fingerprint, analysis_configuration, prepare_output
# Compatibility exports: existing notebooks/imports keep their original names.
from tools.analysis_schema import POSITION_FIELDS, GAME_FIELDS, BLUNDER_FIELDS
from tools.analysis_inputs import (
    MAX_OPENING_PLIES, classify, read_json, load_moves, load_pgn, opening_plies_from,
    game_signature, acemi_colors, load_run, build_manifest,
)
from tools.analysis_artifacts import (
    PARTS_DIR, PARTS_MANIFEST, _sha256, _atomic_write, part_id, _part_files,
    read_parts_manifest, valid_parts, processed_game_ids, _blunder_category,
    seal_part, _read_csv_rows, aggregate,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = ROOT / "data" / "runs"
DEFAULT_OUT = ROOT / "data" / "analysis"
PIECE_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
NON_PAWN = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)

FEN_CACHE_LIMIT = 50_000  # Per worker; opening positions repeat across games.
RECHECK_SEED = 20261031

_engine = None
_depth = 10
_tablebase = None
_worker_error: str | None = None
_fen_cache: "OrderedDict[tuple, tuple[int, str | None]]" = OrderedDict()


def _init_worker(stockfish: str, depth: int, syzygy: str | None = None) -> None:
    global _engine, _depth, _tablebase, _worker_error
    _worker_error = None
    _engine = chess.engine.SimpleEngine.popen_uci(stockfish)
    _engine.configure({"Threads": 1, "Hash": 64})
    _depth = depth
    _fen_cache.clear()
    _tablebase = None
    if syzygy:
        try:
            _tablebase = chess_syzygy.open_tablebase(syzygy)
        except Exception:
            _close_worker()
            raise  # A configured tablebase must not silently become a different analysis.


def _close_worker() -> None:
    global _engine, _tablebase
    if _engine is not None:
        _engine.quit()
        _engine = None
    if _tablebase is not None:
        _tablebase.close()
        _tablebase = None


def _sf_eval(board: chess.Board) -> tuple[int, str | None]:
    # EPD (no move counters) as the key, so a position reached in many games is searched once per worker.
    key = (board.epd(), _depth)
    cached = _fen_cache.get(key)
    if cached is not None:
        _fen_cache.move_to_end(key)
        return cached
    info = _engine.analyse(board, chess.engine.Limit(depth=_depth))
    score = info.get("score")
    pv = info.get("pv") or []
    best = pv[0].uci() if pv else None
    if score is None:
        value = 0
    else:
        white = score.pov(chess.WHITE)
        if white.is_mate():
            mate = white.mate()
            value = 10000 - abs(mate) if mate > 0 else -10000 + abs(mate)
        else:
            value = int(white.score())
    _fen_cache[key] = (value, best)
    if len(_fen_cache) > FEN_CACHE_LIMIT:
        _fen_cache.popitem(last=False)
    return value, best


def _tb_wdl(board: chess.Board) -> int | None:
    """Syzygy WDL from White's point of view (2 win .. -2 loss), or None when not probeable."""
    if _tablebase is None or board.castling_rights or len(board.piece_map()) > 5:
        return None
    try:
        value = _tablebase.probe_wdl(board)
    except Exception:  # Table missing or position not covered: the caller falls back to Stockfish.
        return None
    return value if board.turn == chess.WHITE else -value


def outcome_label(sf_cp_white: int, tb_wdl_white: int | None, sign: int) -> tuple[str, str]:
    """('win'|'draw'|'loss', source) for the Acemi side. ``sign`` is +1 for White, -1 for Black.

    A tablebase value wins when present; cursed wins and blessed losses (+-1) count as draws.
    Otherwise Stockfish: at least +200 cp is a win, at most -200 cp a loss.
    """
    if tb_wdl_white is not None:
        value = sign * tb_wdl_white
        return ("win" if value == 2 else "loss" if value == -2 else "draw"), "syzygy"
    value = sign * sf_cp_white
    return ("win" if value >= 200 else "loss" if value <= -200 else "draw"), "stockfish"


def _phase(board: chess.Board, ply: int) -> str:
    non_pawn = sum(len(board.pieces(piece, color)) for piece in NON_PAWN for color in (chess.WHITE, chess.BLACK))
    if ply <= 20:
        return "opening"
    if non_pawn <= 26:
        return "endgame"
    return "middlegame"


def _material(board: chess.Board) -> int:
    return sum(
        PIECE_VALUE.get(piece, 0) * (1 if color == chess.WHITE else -1) * len(board.pieces(piece, color))
        for piece in PIECE_VALUE for color in (chess.WHITE, chess.BLACK)
    )


def _termination(board: chess.Board, headers: dict) -> str:
    if board.is_checkmate():
        return "checkmate"
    if board.is_stalemate():
        return "stalemate"
    if board.is_insufficient_material():
        return "insufficient_material"
    if board.is_fifty_moves():
        return "fifty_moves"
    if board.can_claim_threefold_repetition():
        return "threefold_repetition"
    return str(headers.get("Termination", "normal")) or "normal"


def _result_for(color: str | None, result: str) -> str:
    if result == "1/2-1/2":
        return "draw"
    if result == "1-0":
        return "win" if color == "white" else "loss"
    if result == "0-1":
        return "win" if color == "black" else "loss"
    return "unknown"


def analyze_game(game: dict, depth: int) -> dict:
    pgn_moves = game["pgn_moves"]
    records_by_ply = game["records_by_ply"]
    opening_plies = game.get("opening_plies", 0)
    acemi_sides = set(game["acemi_sides"])
    focus = game["focus_color"]
    evaluations: dict[str, tuple[int, str | None]] = {}
    boards: list[chess.Board] = []
    tb_values: list[int | None] = []
    board = chess.Board()
    for move in pgn_moves:
        fen = board.fen()
        boards.append(board.copy())
        tb_values.append(_tb_wdl(board))
        if fen not in evaluations:
            evaluations[fen] = _sf_eval(board)
        board.push_uci(move)
    final_board = board
    final_eval = evaluations.get(final_board.fen())
    if final_eval is None:
        final_eval = _sf_eval(final_board)
    scores = [evaluations[item.fen()][0] for item in boards] + [final_eval[0]]

    plies: list[dict] = []
    for index, move in enumerate(pgn_moves):
        position = boards[index]
        side = "white" if position.turn == chess.WHITE else "black"
        record = records_by_ply.get(index + 1, {})
        player = record.get("player") or ("opening" if index + 1 <= opening_plies else "unknown")
        is_acemi = player == "engine" or (game["run_type"] == "AB" and player == "opponent")
        before, best = evaluations[position.fen()]
        after = scores[index + 1]
        tb_white = tb_values[index]
        loss = None
        if is_acemi:
            if move == best:
                loss = 0
            elif side == "white":
                loss = max(0, before - after)
            else:
                loss = max(0, after - before)
            loss = min(loss, 2000)
        plies.append(
            {
                "run_name": game["run_name"],
                "run_type": game["run_type"],
                "game_no": game["game_no"],
                "game_id": f"{game['run_name']}#{game['game_no']}",
                "ply": index + 1,
                "side": side,
                "player": player,
                "is_acemi": is_acemi,
                "fen": position.fen(),
                "move": move,
                "acemi_eval_cp": record.get("eval_cp"),
                "acemi_depth": record.get("depth"),
                "sf_cp": before,
                "sf_best_move": best,
                "cp_loss": loss,
                "piece_count": len(position.piece_map()),
                "white_pieces": chess.popcount(position.occupied_co[chess.WHITE]),
                "black_pieces": chess.popcount(position.occupied_co[chess.BLACK]),
                "phase": _phase(position, index + 1),
                "material_balance": _material(position),
                "opening": game["opening"],
                "game_result": game["result"],
                "tb_wdl": "" if tb_white is None else tb_white,
                "label_source": "syzygy" if tb_white is not None else "stockfish",
            }
        )

    focus_sign = 1 if focus == "white" else -1
    focus_scores = [
        focus_sign * scores[index]
        for index in range(len(pgn_moves))
        if ("white" if boards[index].turn == chess.WHITE else "black") == focus
    ] if focus else []
    first_decision = None
    for index in range(len(pgn_moves)):
        side = "white" if boards[index].turn == chess.WHITE else "black"
        if not focus or side != focus:
            continue
        value = focus_sign * scores[index]
        if abs(value) > 150:
            first_decision = index + 1
            break
    first = {5: (None, None, None), 6: (None, None, None), 7: (None, None, None)}
    for index in range(len(pgn_moves)):
        count = len(boards[index].piece_map())
        for limit in (5, 6, 7):
            if first[limit][0] is None and count <= limit:
                label, source = outcome_label(scores[index], tb_values[index], focus_sign)
                first[limit] = (index + 1, label, source)
    first_le5, first_le5_sf, first_le5_source = first[5]
    first_le6, first_le6_sf, first_le6_source = first[6]
    first_le7, first_le7_sf, first_le7_source = first[7]
    focus_losses = [
        row["cp_loss"] for row in plies
        if row["side"] == focus and row["cp_loss"] is not None
    ]
    return {
        "game_id": f"{game['run_name']}#{game['game_no']}",
        "run_name": game["run_name"],
        "run_type": game["run_type"],
        "game_no": game["game_no"],
        "result": game["result"],
        "result_acemi": _result_for(focus, game["result"]),
        "termination": _termination(final_board, {"Termination": game.get("termination_header", "")}),
        "opening": game["opening"],
        "white": game["white"],
        "black": game["black"],
        "focus_color": focus,
        "acemi_sides": sorted(acemi_sides),
        "in_result_sample": game["in_result_sample"],
        "result_sample_proxy": game["result_sample_proxy"],
        "duplicate_games": game.get("duplicate_games", []),
        "move_time_ms": game.get("move_time_ms"),
        "engine_version": game["meta"].get("engine_version"),
        "opponent": game["meta"].get("opponent", {}),
        "engine_settings": game["meta"].get("engine_settings", {}),
        "opening_set": game["meta"].get("opening_set"),
        "plies": plies,
        "game_stats": {
            "game_id": f"{game['run_name']}#{game['game_no']}",
            "run_name": game["run_name"],
            "run_type": game["run_type"],
            "game_no": game["game_no"],
            "result": game["result"],
            "result_acemi": _result_for(focus, game["result"]),
            "termination": _termination(final_board, {"Termination": game.get("termination_header", "")}),
            "opening": game["opening"],
            "focus_color": focus,
            "plies": len(pgn_moves),
            "in_result_sample": game["in_result_sample"],
            "result_sample_proxy": game["result_sample_proxy"],
            "duplicate_count": len(game.get("duplicate_games", [])),
            "acemi_max_sf": max(focus_scores) if focus_scores else None,
            "acemi_min_sf": min(focus_scores) if focus_scores else None,
            "first_decision_ply": first_decision,
            "critical_errors": sum(1 for value in focus_losses if value > 150),
            "opening_plies": opening_plies,
            "first_le5_ply": first_le5,
            "first_le5_sf": first_le5_sf,
            "first_le5_source": first_le5_source,
            "first_le6_ply": first_le6,
            "first_le6_sf": first_le6_sf,
            "first_le6_source": first_le6_source,
            "first_le7_ply": first_le7,
            "first_le7_sf": first_le7_sf,
            "first_le7_source": first_le7_source,
            "final_piece_count": len(final_board.piece_map()),
            "end_phase": _phase(final_board, len(pgn_moves)),
            "final_sf_cp": focus_sign * final_eval[0] if focus else None,
            "engine_options": game["meta"].get("engine_settings", {}).get("extra_options"),
            "opponent_options": game["meta"].get("opponent", {}).get("extra_options"),
            "uci_elo": game["meta"].get("opponent", {}).get("uci_elo"),
            "move_time_ms": game.get("move_time_ms"),
            "opening_set": game["meta"].get("opening_set"),
        },
    }


def cache_path(out_dir: Path, game: dict) -> Path:
    identity = active_fingerprint(out_dir)
    digest = hashlib.sha256(f"{identity}:{game['run_name']}#{game['game_no']}".encode()).hexdigest()[:20]
    return out_dir / "cache" / f"{game['run_type']}_{game['run_name'][:40]}_{game['game_no']}_{digest}.json"


def cached_game_exists(out_dir: Path, game: dict) -> bool:
    path = cache_path(out_dir, game)
    try:
        data = read_json(path)
        return (data.get("game_id") == f"{game['run_name']}#{game['game_no']}"
                and data.get("analysis_fingerprint") == active_fingerprint(out_dir)
                and isinstance(data.get("plies"), list) and isinstance(data.get("game_stats"), dict))
    except (OSError, ValueError, AttributeError):
        return False


def _analyze_task(game: dict, out_dir: str, depth: int) -> str:
    if active_fingerprint(Path(out_dir)) is not None:
        configured = read_json(Path(out_dir) / "config.json")["analysis_configuration"]["depth"]
        if configured != depth:
            raise ValueError("Task depth differs from the output analysis configuration")
    path = cache_path(Path(out_dir), game)
    if cached_game_exists(Path(out_dir), game):
        return str(path)
    result = analyze_game(game, depth)
    result["analysis_fingerprint"] = active_fingerprint(Path(out_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, lambda temporary: temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8"))
    return str(path)


def _task_wrapper(args: tuple[dict, str, int]) -> str:
    if _worker_error is not None:
        raise RuntimeError(f"Analysis worker startup failed: {_worker_error}")
    return _analyze_task(*args)


def _init_pool_worker(stockfish: str, depth: int, syzygy: str | None = None) -> None:
    """Deliver startup failures through a task, avoiding Pool's endless respawn loop."""
    global _worker_error
    try:
        _init_worker(stockfish, depth, syzygy)
    except Exception as error:
        _worker_error = f"{type(error).__name__}: {error}"
        try:
            _close_worker()
        except Exception:
            pass  # Preserve the startup failure even if a broken engine cannot quit.


def select_recheck_rows(rows: list[dict], limit: int = 50, per_game: int = 2, seed: int = RECHECK_SEED) -> list[dict]:
    """Deterministic stratified sample: half AB, half SF, at most ``per_game`` per game.

    When one run type has too few blunders the other fills the remaining slots.
    """
    rng = random.Random(seed)
    pools: dict[str, list[dict]] = {}
    for run_type in ("AB", "SF"):
        pool = sorted(
            (row for row in rows if row.get("run_type") == run_type),
            key=lambda row: (row["game_id"], int(row["ply"])),
        )
        rng.shuffle(pool)
        taken: dict[str, int] = {}
        kept = []
        for row in pool:
            if taken.get(row["game_id"], 0) >= per_game:
                continue
            taken[row["game_id"]] = taken.get(row["game_id"], 0) + 1
            kept.append(row)
        pools[run_type] = kept
    half = limit // 2
    chosen = pools["AB"][:half] + pools["SF"][:half]
    spare = pools["AB"][half:] + pools["SF"][half:]
    chosen += spare[: limit - len(chosen)]
    return sorted(chosen, key=lambda row: (row["run_type"], row["game_id"], int(row["ply"])))


def recheck_blunders(out_dir: Path, limit: int = 50, seed: int = RECHECK_SEED) -> dict:
    """Re-search a stratified blunder sample with Acemi at depth 4 and compare the move."""
    source = out_dir / "blunders.csv"
    if not source.exists():
        return {"error": "blunders.csv missing; run the analysis first"}
    candidates = [
        row for row in _read_csv_rows(source) if str(row.get("is_acemi", "")).lower() == "true"
    ]
    rows = select_recheck_rows(candidates, limit, seed=seed)
    engine = chess.engine.SimpleEngine.popen_uci([sys.executable, "-m", "engine"], cwd=str(ROOT))
    output = []
    try:
        for row in rows:
            board = chess.Board(row["fen"])
            played = row.get("move")
            try:
                result = engine.play(board, chess.engine.Limit(depth=4))
                best = result.move.uci() if result.move else None
            except Exception:
                best = None
            output.append(
                {
                    "run_type": row.get("run_type"),
                    "game_id": row.get("game_id"),
                    "ply": row.get("ply"),
                    "fen": row.get("fen"),
                    "played": played,
                    "depth4_best": best,
                    "avoids_blunder": bool(best and played and best != played),
                }
            )
    finally:
        engine.quit()
    path = out_dir / "recheck.csv"
    fields = ["run_type", "game_id", "ply", "fen", "played", "depth4_best", "avoids_blunder"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    meta = {
        "seed": seed,
        "limit": limit,
        "pool": {kind: sum(1 for row in candidates if row.get("run_type") == kind) for kind in ("AB", "SF")},
        "sampled": {kind: sum(1 for row in output if row["run_type"] == kind) for kind in ("AB", "SF")},
        "max_per_game": 2,
    }
    (out_dir / "recheck_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return {"rechecked": len(output), "path": str(path), **meta}


def pgn_terminations(runs_dir: Path) -> dict[str, str]:
    """Correct game terminations directly from the PGN histories (no engine)."""
    result: dict[str, str] = {}
    for run_dir in sorted(runs_dir.iterdir()):
        path = run_dir / "games.pgn.gz"
        if not path.exists():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            while True:
                game = chess.pgn.read_game(stream)
                if game is None:
                    break
                board = game.board()
                for move in game.mainline_moves():
                    board.push(move)
                result[f"{run_dir.name}#{game.headers.get('Round')}"] = _termination(board, dict(game.headers))
    return result


def repair_terminations(out_dir: Path, runs_dir: Path) -> dict:
    """Rewrite termination in games.csv and sealed game parts from PGNs.

    This is a one-time correction for records produced before
    ``can_claim_threefold_repetition`` was used; no Stockfish run is needed.
    """
    mapping = pgn_terminations(runs_dir)
    changed = 0
    games_path = out_dir / "games.csv"
    if games_path.exists():
        with games_path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            rows = list(reader)
        for row in rows:
            new = mapping.get(row.get("game_id", ""))
            if new and row.get("termination") != new:
                row["termination"] = new
                changed += 1
        with games_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    parts_path = out_dir / "parts.json"
    part_changes = 0
    if parts_path.exists():
        manifest = json.loads(parts_path.read_text(encoding="utf-8"))
        for part in manifest.get("parts", []):
            game_file = part.get("files", {}).get("games")
            if not game_file:
                continue
            path = out_dir / game_file["path"]
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames or []
                rows = list(reader)
            local_changed = 0
            for row in rows:
                new = mapping.get(row.get("game_id", ""))
                if new and row.get("termination") != new:
                    row["termination"] = new
                    local_changed += 1
            if local_changed:
                with path.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
                game_file["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                part_changes += local_changed
        parts_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"terminations_from_pgn": len(mapping), "games_changed": changed, "parts_changed": part_changes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze recorded Acemi games with Stockfish.")
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--stockfish", default=None)
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--types", default="AB,SF")
    parser.add_argument("--max-games", type=int, default=None)
    parser.add_argument("--max-new-games", type=int, default=None)
    parser.add_argument("--aggregate-only", action="store_true")
    parser.add_argument("--recheck", action="store_true")
    parser.add_argument("--repair-termination", action="store_true")
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--ms-per-eval", type=float, default=30.0)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--syzygy", default=None, help="directory with Syzygy WDL tables (.rtbw) for <=5-piece labels")
    parser.add_argument("--seed", type=int, default=RECHECK_SEED, help="seed of the recheck sample")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    if args.repair_termination:
        print(repair_terminations(args.out, args.runs))
        return 0
    if args.recheck:
        print(recheck_blunders(args.out, seed=args.seed))
        return 0
    if args.estimate:
        games, stats = build_manifest(args.runs, {item.strip() for item in args.types.split(",")}, args.max_games)
        plies = sum(len(game["pgn_moves"]) for game in games)
        workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
        hours = plies * args.ms_per_eval / 1000.0 / workers / 3600.0
        print(json.dumps({"games": len(games), "plies": plies, "workers": workers,
                          "ms_per_eval": args.ms_per_eval, "estimated_hours": round(hours, 2),
                          "note": "tahmin; gerçek süre CPU ve Stockfish hızına bağlı"}, indent=1))
        return 0
    if not args.aggregate_only:
        games, stats = build_manifest(args.runs, {item.strip() for item in args.types.split(",")}, args.max_games)
        print(json.dumps(stats, indent=1)[:4000])
        if args.smoke:
            games = games[:1]
        stockfish = args.stockfish or os.environ.get("STOCKFISH_PATH") or "/usr/games/stockfish"
        if not Path(stockfish).exists():
            print(f"Stockfish not found at {stockfish}; pass --stockfish or set STOCKFISH_PATH", file=sys.stderr)
            return 1
        try:
            identity_config = analysis_configuration(Path(stockfish), args.depth,
                                                     Path(args.syzygy) if args.syzygy else None)
        except (OSError, ValueError) as error:
            print(f"Invalid analysis configuration: {error}", file=sys.stderr)
            return 1
        try:
            probe = subprocess.run([stockfish, "--version"], capture_output=True, text=True, timeout=10)
            version_line = (probe.stdout + probe.stderr).strip().splitlines()[0]
        except Exception:
            version_line = "unknown"
        config = {
            "stockfish_path": stockfish,
            "stockfish_version": version_line,
            "depth": args.depth,
            "workers": args.workers,
            "types": args.types,
            "syzygy_dir": args.syzygy,
            "syzygy_files": (
                len(list(Path(args.syzygy).glob("*.rtbw"))) if args.syzygy and Path(args.syzygy).is_dir() else 0
            ),
            "generated_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            prepare_output(args.out, identity_config, **config)
            parts, problems = valid_parts(args.out)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        (args.out / "manifest.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
        for problem in problems:
            print(f"WARNING: {problem}; its games will be analysed again")
        processed = {game_id for part in parts for game_id in part["game_ids"]}
        pending = [
            game for game in games
            if not cached_game_exists(args.out, game)
            and f"{game['run_name']}#{game['game_no']}" not in processed
        ]
        if args.max_new_games is not None:
            pending = pending[: args.max_new_games]
        print(f"games in manifest: {len(games)}, pending: {len(pending)}")
        workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
        tasks = [(game, str(args.out), args.depth) for game in pending]
        if workers == 1 and tasks:
            _init_worker(stockfish, args.depth, args.syzygy)
            try:
                for task in tasks:
                    _task_wrapper(task)
            finally:
                _close_worker()
        elif tasks:
            with mp.Pool(workers, initializer=_init_pool_worker, initargs=(stockfish, args.depth, args.syzygy)) as pool:
                for _ in pool.imap_unordered(_task_wrapper, tasks):
                    pass
        elif not pending:
            print("no pending games")
        sealed = seal_part(args.out)
        if sealed:
            print(f"sealed part {sealed['id']}: {sealed['rows']}")
        report = aggregate(args.out)
        print(f"aggregated: {report}")
        if not pending and not sealed and not args.smoke:
            return 2
    else:
        print(f"aggregated: {aggregate(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
