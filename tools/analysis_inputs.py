"""Read immutable run artifacts and build the deduplicated analysis manifest."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import chess
import chess.pgn


MAX_OPENING_PLIES = 20

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
