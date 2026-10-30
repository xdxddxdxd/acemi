"""One-off analysis of recorded Acemi games with Stockfish.

Run types are kept apart: ``AB`` (Acemi vs Acemi, usually a feature switch) and
``SF`` (Acemi vs Stockfish). Demo and AcemiRandom games are ignored.

The tool is resumable: every game is evaluated once and cached under
``data/analysis/cache/``. Re-running skips cached games. ``--max-new-games`` lets
the notebook process a chunk and push, then continue.

    python -m tools.analyze_games --all --depth 10 --workers 3
    python -m tools.analyze_games --all --max-new-games 40 --depth 10 --workers 3
    python -m tools.analyze_games --aggregate
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import multiprocessing as mp
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = ROOT / "data" / "runs"
DEFAULT_OUT = ROOT / "data" / "analysis"
PIECE_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
NON_PAWN = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)

_engine = None
_depth = 10


def _init_worker(stockfish: str, depth: int) -> None:
    global _engine, _depth
    _engine = chess.engine.SimpleEngine.popen_uci(stockfish)
    _engine.configure({"Threads": 1, "Hash": 64})
    _depth = depth


def _close_worker() -> None:
    global _engine
    if _engine is not None:
        _engine.quit()
        _engine = None


def classify(meta: dict) -> str:
    if meta.get("is_demo"):
        return "demo"
    opponent = str(meta.get("opponent", {}).get("name", ""))
    if "Stockfish" in opponent:
        return "SF"
    if opponent == "Acemi":
        return "AB"
    return "other"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_moves(run: Path) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    path = run / "moves.jsonl.gz"
    if not path.exists():
        return grouped
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            grouped.setdefault(record["game_no"], []).append(record)
    for records in grouped.values():
        records.sort(key=lambda item: item["ply"])
    return grouped


def load_pgn(run: Path) -> dict[int, tuple[dict, list[str]]]:
    games: dict[int, tuple[dict, list[str]]] = {}
    path = run / "games.pgn.gz"
    if not path.exists():
        return games
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        while True:
            game = chess.pgn.read_game(stream)
            if game is None:
                break
            try:
                game_no = int(game.headers.get("Round", "0"))
            except ValueError:
                continue
            games[game_no] = (dict(game.headers), [move.uci() for move in game.mainline_moves()])
    return games


def game_signature(game: dict) -> tuple:
    return (tuple(game.get("pgn_moves", [])), game.get("result", ""))


def acemi_colors(run_type: str, headers: dict, records: list[dict]) -> tuple[list[str], str | None]:
    if run_type == "SF":
        white = str(headers.get("White", ""))
        black = str(headers.get("Black", ""))
        if white.startswith("Acemi"):
            return ["white"], "white"
        if black.startswith("Acemi"):
            return ["black"], "black"
        return [], None
    colors = {record.get("side") for record in records if record.get("player") == "engine"}
    return ["white", "black"], (next(iter(colors)) if len(colors) == 1 else None)


def load_run(run: Path) -> tuple[dict, list[dict]]:
    meta = read_json(run / "meta.json")
    results = read_json(run / "results.json")
    run_type = classify(meta)
    if run_type not in ("AB", "SF"):
        return {"meta": meta, "results": results, "run_type": run_type, "path": run, "games": []}, []
    moves_by_game = load_moves(run)
    pgn_by_game = load_pgn(run)
    pgn_count = len(pgn_by_game)
    counted = int(results.get("games", 0))
    # Records do not identify post-decision games individually. Use the recorded
    # count as a proxy: exclude the last (pgn_count - counted) games by game_no.
    excluded_tail = max(0, pgn_count - counted)
    game_numbers = sorted(pgn_by_game)
    excluded = set(game_numbers[-excluded_tail:]) if excluded_tail else set()
    games: list[dict] = []
    for game_no in game_numbers:
        headers, pgn_moves = pgn_by_game[game_no]
        if not pgn_moves:
            continue
        records_by_ply = {record["ply"]: record for record in moves_by_game.get(game_no, [])}
        result = str(headers.get("Result", "*"))
        acemi_sides, focus = acemi_colors(run_type, headers, list(records_by_ply.values()))
        opening_text = str(headers.get("Opening", ""))
        opening_plies = len(opening_text.split(":")[-1].split()) if ":" in opening_text else 0
        if not acemi_sides:
            continue
        games.append(
            {
                "run_name": run.name,
                "run_type": run_type,
                "game_no": game_no,
                "result": result,
                "termination_header": headers.get("Termination", ""),
                "opening": headers.get("Opening", ""),
                "white": headers.get("White", ""),
                "black": headers.get("Black", ""),
                "move_time_ms": headers.get("MoveTimeMs", ""),
                "acemi_sides": acemi_sides,
                "focus_color": focus,
                "in_result_sample": game_no not in excluded,
                "result_sample_proxy": excluded_tail > 0,
                "pgn_moves": pgn_moves,
                "records_by_ply": records_by_ply,
                "opening_plies": opening_plies,
                "meta": {
                    "engine_version": meta.get("engine_version"),
                    "opponent": meta.get("opponent", {}),
                    "engine_settings": meta.get("engine_settings", {}),
                    "opening_set": meta.get("opening_set"),
                    "hardware": meta.get("hardware", {}),
                },
            }
        )
    return {"meta": meta, "results": results, "run_type": run_type, "path": run, "games": games}, games


def build_manifest(runs_dir: Path, types: set[str], max_games: int | None = None) -> tuple[list[dict], dict]:
    runs = sorted(path for path in runs_dir.iterdir() if (path / "meta.json").exists())
    all_games: list[dict] = []
    stats = {"runs_total": len(runs), "runs_used": 0, "games_total": 0, "games_used": 0,
             "excluded_demo_other": 0, "excluded_missing_moves": 0, "duplicates": 0,
             "by_type": {}, "runs": []}
    for run in runs:
        info, games = load_run(run)
        if info["run_type"] not in types:
            stats["excluded_demo_other"] += len(games)
            continue
        stats["runs_used"] += 1
        stats["games_total"] += len(games)
        stats["by_type"].setdefault(info["run_type"], 0)
        stats["by_type"][info["run_type"]] += len(games)
        stats["runs"].append({"name": run.name, "type": info["run_type"], "games": len(games),
                              "counted": info["results"].get("games"),
                              "post_decision": info["results"].get("post_decision_games_excluded", 0)})
        all_games.extend(games)

    # Deduplicate within each run type. Prefer a game that belongs to the counted
    # result sample, then the earliest run name.
    all_games.sort(key=lambda game: (game["run_type"], not game["in_result_sample"], game["run_name"], game["game_no"]))
    unique: dict[tuple, dict] = {}
    duplicates: dict[tuple, list[str]] = {}
    for game in all_games:
        key = (game["run_type"], game_signature(game))
        if key in unique:
            stats["duplicates"] += 1
            duplicates.setdefault(key, []).append(f"{game['run_name']}#{game['game_no']}")
            continue
        unique[key] = game
    for key, game in unique.items():
        game["duplicate_games"] = duplicates.get(key, [])
    chosen = list(unique.values())
    chosen.sort(key=lambda game: (game["run_type"], game["run_name"], game["game_no"]))
    if max_games is not None:
        chosen = chosen[:max_games]
    stats["games_used"] = len(chosen)
    return chosen, stats


def _sf_eval(board: chess.Board) -> tuple[int, str | None]:
    info = _engine.analyse(board, chess.engine.Limit(depth=_depth))
    score = info.get("score")
    pv = info.get("pv") or []
    best = pv[0].uci() if pv else None
    if score is None:
        return 0, best
    white = score.pov(chess.WHITE)
    if white.is_mate():
        mate = white.mate()
        value = 10000 - abs(mate) if mate > 0 else -10000 + abs(mate)
        return value, best
    return int(white.score()), best


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
    if board.is_repetition(3):
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
    board = chess.Board()
    for move in pgn_moves:
        fen = board.fen()
        boards.append(board.copy())
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
    first_le5 = first_le6 = first_le7 = None
    first_le5_sf = first_le6_sf = first_le7_sf = None
    for index in range(len(pgn_moves)):
        position = boards[index]
        count = len(position.piece_map())
        value = focus_sign * scores[index]
        if first_le5 is None and count <= 5:
            first_le5 = index + 1
            first_le5_sf = "win" if value >= 200 else "loss" if value <= -200 else "draw"
        if first_le6 is None and count <= 6:
            first_le6 = index + 1
            first_le6_sf = "win" if value >= 200 else "loss" if value <= -200 else "draw"
        if first_le7 is None and count <= 7:
            first_le7 = index + 1
            first_le7_sf = "win" if value >= 200 else "loss" if value <= -200 else "draw"
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
            "first_le5_ply": first_le5,
            "first_le5_sf": first_le5_sf,
            "first_le6_ply": first_le6,
            "first_le6_sf": first_le6_sf,
            "first_le7_ply": first_le7,
            "first_le7_sf": first_le7_sf,
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
    digest = hashlib.sha1(f"{game['run_name']}#{game['game_no']}".encode()).hexdigest()[:12]
    return out_dir / "cache" / f"{game['run_type']}_{game['run_name'][:40]}_{game['game_no']}_{digest}.json"


def _analyze_task(game: dict, out_dir: str, depth: int) -> str:
    path = cache_path(Path(out_dir), game)
    if path.exists():
        return str(path)
    result = analyze_game(game, depth)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _task_wrapper(args: tuple[dict, str, int]) -> str:
    return _analyze_task(*args)


def _read_existing_positions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_existing_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def aggregate(out_dir: Path) -> dict:
    caches = sorted((out_dir / "cache").glob("*.json"))
    cached_games: dict[str, dict] = {}
    cached_positions: dict[tuple, dict] = {}
    for cache in caches:
        data = json.loads(cache.read_text(encoding="utf-8"))
        game_id = data["game_id"]
        cached_games[game_id] = data["game_stats"]
        for row in data["plies"]:
            cached_positions[(game_id, row["ply"])] = row
    existing_games = {row["game_id"]: row for row in _read_existing_csv(out_dir / "games.csv")}
    existing_positions = {
        (row["game_id"], row["ply"]): row for row in _read_existing_positions(out_dir / "positions.csv.gz")
    }
    existing_games.update(cached_games)
    existing_positions.update(cached_positions)
    # A cached game replaces every existing row of that game.
    for game_id in cached_games:
        for key in [key for key in existing_positions if key[0] == game_id and key not in cached_positions]:
            del existing_positions[key]
    games = list(existing_games.values())
    positions = list(existing_positions.values())
    out_dir.mkdir(parents=True, exist_ok=True)
    position_fields = [
        "run_name", "run_type", "game_no", "game_id", "ply", "side", "player", "is_acemi",
        "fen", "move", "acemi_eval_cp", "acemi_depth", "sf_cp", "sf_best_move", "cp_loss",
        "piece_count", "white_pieces", "black_pieces", "phase", "material_balance", "opening", "game_result",
    ]
    with gzip.open(out_dir / "positions.csv.gz", "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=position_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(positions)
    game_fields = [
        "game_id", "run_name", "run_type", "game_no", "result", "result_acemi", "termination", "opening",
        "focus_color", "plies", "in_result_sample", "result_sample_proxy", "duplicate_count",
        "acemi_max_sf", "acemi_min_sf", "first_decision_ply", "critical_errors",
        "first_le5_ply", "first_le5_sf", "first_le6_ply", "first_le6_sf",
        "first_le7_ply", "first_le7_sf", "final_piece_count", "end_phase", "final_sf_cp",
        "engine_options", "opponent_options", "uci_elo", "move_time_ms", "opening_set",
    ]
    with (out_dir / "games.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=game_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(games)
    blunders = []
    for row in positions:
        if row["is_acemi"] and row["cp_loss"] not in (None, "") and float(row["cp_loss"]) > 150:
            board = chess.Board(row["fen"])
            move = chess.Move.from_uci(row["move"]) if row["move"] else None
            tactical = bool(
                move and (board.is_capture(move) or board.gives_check(move) or move.promotion)
            )
            blunders.append({**row, "category": "tactical" if tactical else "positional"})
    with (out_dir / "blunders.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=position_fields + ["category"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(blunders)
    processed = sorted({game_id for game_id, _ply in existing_positions})
    text = "\n".join(processed) + ("\n" if processed else "")
    (out_dir / "processed_games.txt").write_text(text, encoding="utf-8")
    return {"games": len(games), "positions": len(positions), "blunders": len(blunders)}


def recheck_blunders(out_dir: Path, limit: int = 50) -> dict:
    """Re-search sampled blunders with Acemi at depth 4 and compare the move."""
    source = out_dir / "blunders.csv"
    if not source.exists():
        return {"error": "blunders.csv missing; run the analysis first"}
    rows = list(csv.DictReader(source.open(encoding="utf-8", newline="")))
    rows = [row for row in rows if str(row.get("is_acemi", "")).lower() == "true"][:limit]
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
    fields = ["game_id", "ply", "fen", "played", "depth4_best", "avoids_blunder"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    return {"rechecked": len(output), "path": str(path)}


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
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--ms-per-eval", type=float, default=30.0)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    if args.recheck:
        print(recheck_blunders(args.out))
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
        (args.out / "manifest.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(stats, indent=1)[:4000])
        if args.smoke:
            games = games[:1]
        stockfish = args.stockfish or os.environ.get("STOCKFISH_PATH") or "/usr/games/stockfish"
        if not Path(stockfish).exists():
            print(f"Stockfish not found at {stockfish}; pass --stockfish or set STOCKFISH_PATH", file=sys.stderr)
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
            "generated_utc": datetime.now(timezone.utc).isoformat(),
        }
        (args.out / "config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
        processed_path = args.out / "processed_games.txt"
        processed = set(processed_path.read_text(encoding="utf-8").splitlines()) if processed_path.exists() else set()
        pending = [
            game for game in games
            if not cache_path(args.out, game).exists()
            and f"{game['run_name']}#{game['game_no']}" not in processed
        ]
        if args.max_new_games is not None:
            pending = pending[: args.max_new_games]
        print(f"games in manifest: {len(games)}, pending: {len(pending)}")
        workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
        tasks = [(game, str(args.out), args.depth) for game in pending]
        if workers == 1:
            _init_worker(stockfish, args.depth)
            try:
                for task in tasks:
                    _task_wrapper(task)
            finally:
                _close_worker()
        elif tasks:
            with mp.Pool(workers, initializer=_init_worker, initargs=(stockfish, args.depth)) as pool:
                for _ in pool.imap_unordered(_task_wrapper, tasks):
                    pass
        elif not pending:
            print("no pending games")
        report = aggregate(args.out)
        print(f"aggregated: {report}")
        if not pending and not args.smoke:
            return 2
    else:
        print(f"aggregated: {aggregate(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
