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

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = ROOT / "data" / "runs"
DEFAULT_OUT = ROOT / "data" / "analysis"
PIECE_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
NON_PAWN = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)

PARTS_DIR = "parts"
PARTS_MANIFEST = "parts.json"
FEN_CACHE_LIMIT = 50_000  # Per worker; opening positions repeat across games.
MAX_OPENING_PLIES = 20
RECHECK_SEED = 20261031
POSITION_FIELDS = [
    "run_name", "run_type", "game_no", "game_id", "ply", "side", "player", "is_acemi",
    "fen", "move", "acemi_eval_cp", "acemi_depth", "sf_cp", "sf_best_move", "cp_loss",
    "piece_count", "white_pieces", "black_pieces", "phase", "material_balance", "opening",
    "game_result", "tb_wdl", "label_source",
]
GAME_FIELDS = [
    "game_id", "run_name", "run_type", "game_no", "result", "result_acemi", "termination", "opening",
    "focus_color", "plies", "opening_plies", "in_result_sample", "result_sample_proxy", "duplicate_count",
    "acemi_max_sf", "acemi_min_sf", "first_decision_ply", "critical_errors",
    "first_le5_ply", "first_le5_sf", "first_le5_source", "first_le6_ply", "first_le6_sf",
    "first_le6_source", "first_le7_ply", "first_le7_sf", "first_le7_source",
    "final_piece_count", "end_phase", "final_sf_cp",
    "engine_options", "opponent_options", "uci_elo", "move_time_ms", "opening_set",
]
BLUNDER_FIELDS = POSITION_FIELDS + ["category"]

_engine = None
_depth = 10
_tablebase = None
_fen_cache: "OrderedDict[tuple, tuple[int, str | None]]" = OrderedDict()


def _init_worker(stockfish: str, depth: int, syzygy: str | None = None) -> None:
    global _engine, _depth, _tablebase
    _engine = chess.engine.SimpleEngine.popen_uci(stockfish)
    _engine.configure({"Threads": 1, "Hash": 64})
    _depth = depth
    _fen_cache.clear()
    _tablebase = None
    if syzygy:
        try:
            _tablebase = chess_syzygy.open_tablebase(syzygy)
        except Exception as error:  # Missing directory or unreadable tables: fall back to Stockfish labels.
            print(f"Syzygy unavailable ({error}); labelling with Stockfish only.", file=sys.stderr)
            _tablebase = None


def _close_worker() -> None:
    global _engine, _tablebase
    if _engine is not None:
        _engine.quit()
        _engine = None
    if _tablebase is not None:
        _tablebase.close()
        _tablebase = None


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


def opening_plies_from(records_by_ply: dict, headers: dict) -> tuple[int, str]:
    """Forced opening plies and where the number came from.

    The first recorded move is the first one a player chose, so everything before it
    was the opening line. Capped at ``MAX_OPENING_PLIES``. Without records the older
    ``Opening: moves`` header form is used when present.
    """
    if records_by_ply:
        return max(0, min(min(records_by_ply) - 1, MAX_OPENING_PLIES)), "first_record"
    text = str(headers.get("Opening", ""))
    if ":" in text:
        return min(len(text.split(":")[-1].split()), MAX_OPENING_PLIES), "header"
    return 0, "none"


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
        opening_plies, opening_plies_source = opening_plies_from(records_by_ply, headers)
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
                "opening_plies_source": opening_plies_source,
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, write) -> None:
    """Write through a temporary file, then rename: readers never see half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    write(temporary)
    os.replace(temporary, path)


def part_id(game_ids) -> str:
    """Content-based id: the same set of games always gives the same part."""
    return hashlib.sha256("\n".join(sorted(game_ids)).encode("utf-8")).hexdigest()[:10]


def _part_files(part: str) -> dict[str, str]:
    return {
        "positions": f"{PARTS_DIR}/positions_part_{part}.csv.gz",
        "games": f"{PARTS_DIR}/games_part_{part}.csv",
        "blunders": f"{PARTS_DIR}/blunders_part_{part}.csv",
    }


def read_parts_manifest(out_dir: Path) -> dict:
    path = out_dir / PARTS_MANIFEST
    if not path.exists():
        return {"parts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"parts": []}
    return data if isinstance(data.get("parts"), list) else {"parts": []}


def valid_parts(out_dir: Path) -> tuple[list[dict], list[str]]:
    """Manifest parts whose files exist with the recorded checksums, plus a list of problems."""
    good: list[dict] = []
    problems: list[str] = []
    seen: set[str] = set()
    for part in read_parts_manifest(out_dir)["parts"]:
        files = part.get("files", {})
        ids = part.get("game_ids", [])
        broken = [name for name in ("positions", "games", "blunders") if name not in files]
        for name, info in files.items():
            path = out_dir / info.get("path", "")
            if not path.exists() or _sha256(path) != info.get("sha256"):
                broken.append(name)
        if broken or part.get("id") != part_id(ids) or seen.intersection(ids):
            problems.append(f"part {part.get('id')} dropped ({', '.join(sorted(set(broken))) or 'bad id or duplicate games'})")
            continue
        seen.update(ids)
        good.append(part)
    return good, problems


def processed_game_ids(out_dir: Path) -> set[str]:
    ids: set[str] = set()
    for part in valid_parts(out_dir)[0]:
        ids.update(part["game_ids"])
    return ids


def _blunder_category(row: dict) -> str:
    board = chess.Board(row["fen"])
    move = chess.Move.from_uci(row["move"]) if row.get("move") else None
    tactical = bool(move and (board.is_capture(move) or board.gives_check(move) or move.promotion))
    return "tactical" if tactical else "positional"


def seal_part(out_dir: Path) -> dict | None:
    """Turn every cached game that is not yet in a part into one immutable part."""
    cache_dir = out_dir / "cache"
    done = processed_game_ids(out_dir)
    cached: dict[str, dict] = {}
    cache_paths: dict[str, Path] = {}
    for path in sorted(cache_dir.glob("*.json")) if cache_dir.exists() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            path.unlink(missing_ok=True)  # Half-written cache entry: the game is analysed again.
            continue
        if data["game_id"] in done:
            path.unlink(missing_ok=True)
            continue
        cached[data["game_id"]] = data
        cache_paths[data["game_id"]] = path
    if not cached:
        return None
    ids = sorted(cached)
    part = part_id(ids)
    files = _part_files(part)

    positions = [row for game_id in ids for row in cached[game_id]["plies"]]
    games = [cached[game_id]["game_stats"] for game_id in ids]
    blunders = []
    for row in positions:
        if row["is_acemi"] and row["cp_loss"] is not None and row["cp_loss"] > 150:
            blunders.append({**row, "category": _blunder_category(row)})

    def write_positions(path: Path) -> None:
        with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=POSITION_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(positions)

    def csv_writer(fields: list[str], rows: list[dict]):
        def write(path: Path) -> None:
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

        return write

    _atomic_write(out_dir / files["positions"], write_positions)
    _atomic_write(out_dir / files["games"], csv_writer(GAME_FIELDS, games))
    _atomic_write(out_dir / files["blunders"], csv_writer(BLUNDER_FIELDS, blunders))
    entry = {
        "id": part,
        "game_ids": ids,
        "rows": {"positions": len(positions), "games": len(games), "blunders": len(blunders)},
        "files": {name: {"path": path, "sha256": _sha256(out_dir / path)} for name, path in files.items()},
        "sealed_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest = {"parts": [item for item in valid_parts(out_dir)[0] if item["id"] != part] + [entry]}
    # The manifest is written last: until then the new files are unreferenced and harmless.
    _atomic_write(
        out_dir / PARTS_MANIFEST,
        lambda path: path.write_text(json.dumps(manifest, indent=1), encoding="utf-8"),
    )
    for path in cache_paths.values():
        path.unlink(missing_ok=True)  # The sealed part is now the source of truth.
    return entry


def _read_csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def aggregate(out_dir: Path) -> dict:
    """Rebuild the small merged files (games.csv, blunders.csv) from the sealed parts.

    Positions are never merged: the report reads the part files directly.
    """
    parts, problems = valid_parts(out_dir)
    games: list[dict] = []
    blunders: list[dict] = []
    positions = 0
    for part in parts:
        games.extend(_read_csv_rows(out_dir / part["files"]["games"]["path"]))
        blunders.extend(_read_csv_rows(out_dir / part["files"]["blunders"]["path"]))
        positions += part["rows"]["positions"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, fields, rows in (("games.csv", GAME_FIELDS, games), ("blunders.csv", BLUNDER_FIELDS, blunders)):
        def write(path: Path, fields=fields, rows=rows) -> None:
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

        _atomic_write(out_dir / name, write)
    ids = sorted(game["game_id"] for game in games)
    (out_dir / "processed_games.txt").write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
    return {"parts": len(parts), "games": len(games), "positions": positions, "blunders": len(blunders),
            "problems": problems}


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
    parser.add_argument("--syzygy", default=None, help="directory with Syzygy WDL tables (.rtbw) for <=5-piece labels")
    parser.add_argument("--seed", type=int, default=RECHECK_SEED, help="seed of the recheck sample")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
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
            "syzygy_dir": args.syzygy,
            "syzygy_files": (
                len(list(Path(args.syzygy).glob("*.rtbw"))) if args.syzygy and Path(args.syzygy).is_dir() else 0
            ),
            "generated_utc": datetime.now(timezone.utc).isoformat(),
        }
        (args.out / "config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
        parts, problems = valid_parts(args.out)
        for problem in problems:
            print(f"WARNING: {problem}; its games will be analysed again")
        processed = {game_id for part in parts for game_id in part["game_ids"]}
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
            _init_worker(stockfish, args.depth, args.syzygy)
            try:
                for task in tasks:
                    _task_wrapper(task)
            finally:
                _close_worker()
        elif tasks:
            with mp.Pool(workers, initializer=_init_worker, initargs=(stockfish, args.depth, args.syzygy)) as pool:
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
