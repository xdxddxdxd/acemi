"""Parallel match runner: Acemi against a UCI opponent, recorded as schema v1.

Example (from the repository root):

    python -m tools.match --games 4 --movetime-ms 300 --uci-elo 1320

Every game is played in its own pair of engine processes. Games run in
parallel (at most one per CPU core). Openings are played in colour-swapped
pairs: game 2k has Acemi as White, game 2k+1 repeats the same opening with
Acemi as Black. python-chess is the independent arbiter for legality, draw
claims and results; the engine's own board is mirrored in parallel and any
disagreement is counted and logged.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shlex
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import chess
    import chess.pgn
except ImportError:  # pragma: no cover - environment problem, not a logic path
    raise SystemExit(
        "python-chess is required for tools/match.py. "
        "Install it with: python -m pip install -r requirements-tools.txt"
    ) from None

from tools import elo as elo_tools  # noqa: E402
from tools import pairing  # noqa: E402
from tools import record, summarize  # noqa: E402
from tools import sprt as sprt_tools  # noqa: E402
from tools.uci_client import (  # noqa: E402
    EngineSetupError,
    UciEngine,
)

# Keep the existing import paths available to notebooks and embedding callers.
from tools.match_openings import (  # noqa: E402
    BUILTIN_SET_NAME, BUILTIN_OPENINGS, Opening, builtin_openings, load_openings,
)
from tools.match_game import (  # noqa: E402
    PGN_TERMINATION, OPENING_PLIES_MAX, ENDGAME_MATERIAL_MAX, PIECE_POINTS,
    _start_engine, book_settings, _mirror_move, _parse_legal, _end_phase,
    _engine_result, _build_pgn, _play_moves, play_game,
)
from tools.match_config import (  # noqa: E402
    STOCKFISH_CANDIDATES, _split_name_version, _git_info, _ram_mb, _cpu_model,
    _find_stockfish, _split_command, parse_option_assignments, parse_args,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    return parse_args(argv, description=__doc__)

SCHEMA_VERSION = record.SCHEMA_VERSION


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        extra_engine_options = parse_option_assignments(args.engine_option)
        extra_opponent_options = parse_option_assignments(args.opponent_option)
    except ValueError as error:
        print(f"Bad option: {error}", file=sys.stderr)
        return 2
    root = Path(args.root)
    cores = os.cpu_count() or 1
    concurrency = args.concurrency if args.concurrency is not None else max(1, cores - 1)
    if concurrency > cores:
        print(f"Limiting concurrency {concurrency} to the {cores} available cores.")
        concurrency = cores
    concurrency = max(1, concurrency)

    if args.openings:
        opening_set, openings = load_openings(Path(args.openings))
    else:
        opening_set, openings = BUILTIN_SET_NAME, builtin_openings()

    engine_cmd = (
        _split_command(args.engine_cmd) if args.engine_cmd else [sys.executable, "-u", "-m", "engine"]
    )
    engine_cwd = args.engine_cwd or str(ROOT)
    if args.opponent_cmd:
        opponent_cmd = _split_command(args.opponent_cmd)
        uci_elo = args.uci_elo
    else:
        stockfish = _find_stockfish(args.stockfish_path)
        if stockfish is None:
            print("Stockfish not found. Pass --stockfish-path or --opponent-cmd.", file=sys.stderr)
            return 2
        opponent_cmd = [stockfish]
        uci_elo = args.uci_elo if args.uci_elo is not None else 1320

    base_engine_options: list[list] = [["Hash", args.hash_mb, False], ["Threads", 1, False]]
    base_opponent_options: list[list] = [["Hash", args.hash_mb, False], ["Threads", 1, False]]
    if uci_elo is not None:
        base_opponent_options += [["UCI_LimitStrength", True, True], ["UCI_Elo", uci_elo, True]]
    base_engine_options += extra_engine_options
    base_opponent_options += extra_opponent_options

    # Preflight: start both engines once to read their names and validate options.
    log_lines: list[str] = []
    names: dict[str, str] = {}
    books: dict[str, dict] = {}
    for label, command, cwd, options in (
        ("engine", engine_cmd, engine_cwd, base_engine_options),
        ("opponent", opponent_cmd, args.opponent_cwd, base_opponent_options),
    ):
        probe = UciEngine(command, label=label, cwd=cwd, log=log_lines)
        try:
            _start_engine(probe, options)
            names[label] = probe.name
            books[label] = book_settings(probe, options)
        except EngineSetupError as error:
            print(f"Setup failed: {error}", file=sys.stderr)
            return 2
        finally:
            probe.close()
    engine_name, engine_version = _split_name_version(names["engine"])
    opponent_name, opponent_version = _split_name_version(names["opponent"])
    print(f"Engine: {names['engine']} | Opponent: {names['opponent']} | uci_elo={uci_elo}")

    started = datetime.now(timezone.utc)
    date_key = started.strftime("%Y%m%dT%H%M%SZ")
    git = _git_info(ROOT, args.git_commit)

    def make_job(game_no: int) -> dict:
        opening_id = (game_no // 2) % len(openings)
        opening = openings[opening_id]
        return {
            "game_no": game_no,
            "pair_no": game_no // 2,
            "opening_id": opening_id,
            "opening": {"name": opening.name, "start_fen": opening.start_fen, "moves": list(opening.moves)},
            "engine_is_white": game_no % 2 == 0,
            "engine_cmd": engine_cmd,
            "engine_cwd": engine_cwd,
            "opponent_cmd": opponent_cmd,
            "opponent_cwd": args.opponent_cwd,
            "engine_options": base_engine_options + [["Seed", args.seed + game_no, False]],
            "opponent_options": base_opponent_options + [["Seed", args.seed + game_no + 1_000_003, False]],
            "movetime_ms": args.movetime_ms,
            "grace_ms": args.grace_ms,
            "max_plies": args.max_plies,
            "event": f"Acemi {engine_version} vs {opponent_name} {opponent_version}",
            "pgn_date": started.strftime("%Y.%m.%d"),
            "engine_name": f"{engine_name} {engine_version}",
            "opponent_name": f"{opponent_name} {opponent_version}",
        }

    games: list[dict] = []
    totals = {"win": 0, "draw": 0, "loss": 0}
    fatal: str | None = None
    stop = False
    decided_games: list[dict] | None = None  # Finished games at the moment the SPRT decided.
    next_game = 0
    pending: set = set()
    with ProcessPoolExecutor(max_workers=concurrency) as pool:
        while True:
            while not stop and len(pending) < concurrency and next_game < args.games:
                pending.add(pool.submit(play_game, make_job(next_game)))
                next_game += 1
            if not pending:
                break
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                try:
                    game = future.result()
                except Exception as error:  # noqa: BLE001 - worker process died
                    fatal = f"worker failed: {error!r}"
                    stop = True
                    continue
                if "fatal" in game:
                    fatal = game["fatal"]
                    stop = True
                    continue
                games.append(game)
                if game["engine_result"] in totals:
                    totals[game["engine_result"]] += 1
                print(
                    f"game {game['game_no']}: Acemi {game['engine_color']} -> {game['engine_result']} "
                    f"({game['termination']}, {game['plies']} plies) | "
                    f"W/D/L {totals['win']}/{totals['draw']}/{totals['loss']}",
                    flush=True,
                )
            if args.sprt and not stop:
                paired_games = pairing.completed_pairs(games)
                paired_wins = sum(g["engine_result"] == "win" for g in paired_games)
                paired_draws = sum(g["engine_result"] == "draw" for g in paired_games)
                paired_losses = sum(g["engine_result"] == "loss" for g in paired_games)
                state = sprt_tools.status(
                    paired_wins, paired_draws, paired_losses, args.elo0, args.elo1, args.alpha, args.beta
                )
                if state.decision != "continue":
                    stop = True
                    decided_games = list(games)
    if fatal is not None:
        print(f"Run aborted: {fatal}", file=sys.stderr)
        return 2

    finished = datetime.now(timezone.utc)
    games.sort(key=lambda item: item["game_no"])
    completed_all = [g for g in games if g["engine_result"] != "aborted"]
    sample = pairing.select_sample(games, sprt_enabled=args.sprt, decided_games=decided_games)
    completed = sample.games
    wins = sum(g["engine_result"] == "win" for g in completed)
    draws = sum(g["engine_result"] == "draw" for g in completed)
    losses = sum(g["engine_result"] == "loss" for g in completed)
    unpaired_games_excluded = sample.unpaired_excluded

    def color_counts(color: str) -> dict:
        subset = [g for g in completed if g["engine_color"] == color]
        return {
            "wins": sum(g["engine_result"] == "win" for g in subset),
            "draws": sum(g["engine_result"] == "draw" for g in subset),
            "losses": sum(g["engine_result"] == "loss" for g in subset),
        }

    def forfeits(reason: str) -> int:
        return sum(
            1 for g in games if g["forfeit"] and g["forfeit"]["who"] == "engine" and g["forfeit"]["reason"] == reason
        )

    engine_moves = [m for g in completed for m in g["moves"] if m["player"] == "engine"]
    depths = [m["depth"] for m in engine_moves if m["depth"] is not None]
    timed = [m for m in engine_moves if m["nodes"] is not None and m["time_ms"] > 0]
    nodes_per_second = (
        round(sum(m["nodes"] for m in timed) / (sum(m["time_ms"] for m in timed) / 1000.0))
        if timed
        else None
    )

    terminations: dict[str, int] = {}
    for g in completed:
        terminations[g["termination"]] = terminations.get(g["termination"], 0) + 1
    search_timed = [m for m in engine_moves if m["nodes"] is not None and m.get("search_time_ms")]
    nodes_per_second_search = (
        round(sum(m["nodes"] for m in search_timed) / (sum(m["search_time_ms"] for m in search_timed) / 1000.0))
        if search_timed
        else None
    )
    moves_without_score = sum(1 for m in engine_moves if m["eval_cp"] is None and m["eval_mate"] is None)

    estimate = elo_tools.estimate(wins, draws, losses)
    if args.sprt:
        state = sprt_tools.status(wins, draws, losses, args.elo0, args.elo1, args.alpha, args.beta)
        sprt_block = {
            "enabled": True,
            "elo0": args.elo0,
            "elo1": args.elo1,
            "alpha": args.alpha,
            "beta": args.beta,
            "max_games": args.games,
            "llr": round(state.llr, 4),
            "lower_bound": round(state.lower_bound, 4),
            "upper_bound": round(state.upper_bound, 4),
            "decision": "inconclusive" if state.decision == "continue" else state.decision,
        }
    else:
        sprt_block = {
            "enabled": False,
            "elo0": args.elo0,
            "elo1": args.elo1,
            "alpha": args.alpha,
            "beta": args.beta,
            "max_games": args.games,
            "llr": None,
            "lower_bound": None,
            "upper_bound": None,
            "decision": "not_run",
        }

    opponent_label = f"{opponent_name} {opponent_version}".strip()
    if uci_elo is not None:
        opponent_label += f" UCI_Elo {uci_elo}"
    if extra_opponent_options:
        opponent_label += " " + ",".join(f"{name}={str(value).lower()}" for name, value, _ in extra_opponent_options)
    slug = re.sub(r"[^a-z0-9.]+", "-", opponent_label.lower()).strip("-")
    short_hash = (git["commit"] or hashlib.sha1(date_key.encode()).hexdigest())[:7]
    run_name = f"{date_key}_{engine_version}_{slug}_{short_hash}"

    meta = {
        "schema_version": SCHEMA_VERSION,
        "run_name": run_name,
        "is_demo": False,
        "date": date_key,
        "engine_name": engine_name,
        "engine_version": engine_version,
        "git_commit": git["commit"] or "unknown",
        "git_dirty": git["dirty"],
        "engine_settings": {
            "move_time_ms": args.movetime_ms,
            "hash_mb": args.hash_mb,
            "random_seed": args.seed,
            **books["engine"],
            "extra_options": {name: value for name, value, _ in extra_engine_options},
        },
        "opponent": {
            "name": opponent_name,
            "version": opponent_version,
            "uci_elo": uci_elo,
            **books["opponent"],
            "extra_options": {name: value for name, value, _ in extra_opponent_options},
        },
        "opening_set": opening_set,
        "match_settings": {
            "games_requested": args.games,
            "concurrency": concurrency,
            "max_plies": args.max_plies,
            "timeout_grace_ms": args.grace_ms,
            "pairing": "colour_swapped_pairs",
            "command": shlex.join(["python", "-m", "tools.match", *(sys.argv[1:] if argv is None else argv)]),
        },
        "hardware": {
            "cpu_count": cores,
            "ram_mb": _ram_mb(),
            "cpu_model": _cpu_model(),
            "runtime": platform.python_implementation(),
            "runtime_version": platform.python_version(),
        },
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
    }
    results = {
        "schema_version": SCHEMA_VERSION,
        "is_demo": False,
        "games": len(completed),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score_pct": None if estimate.score is None else round(100.0 * estimate.score, 1),
        "elo_diff": None if estimate.elo is None else round(estimate.elo, 1),
        "elo_confidence_interval": (
            None
            if not completed
            else [
                None if estimate.low is None else round(estimate.low, 1),
                None if estimate.high is None else round(estimate.high, 1),
            ]
        ),
        "sprt": sprt_block,
        "by_color": {"white": color_counts("white"), "black": color_counts("black")},
        "tactics": None,
        "timeouts": forfeits("timeout"),
        "illegal_moves": forfeits("illegal_move"),
        "engine_crashes": forfeits("crash"),
        "aborted_games": len(games) - len(completed_all),
        "unpaired_games_excluded": unpaired_games_excluded,
        "post_decision_games_excluded": sample.post_decision_excluded,
        "board_disagreements": sum(g["board_disagreements"] for g in games),
        "average_plies": round(sum(g["plies"] for g in completed) / len(completed), 1) if completed else None,
        "average_depth": round(sum(depths) / len(depths), 1) if depths else None,
        "nodes_per_second": nodes_per_second,
        "nodes_per_second_search": nodes_per_second_search,
        "terminations": dict(sorted(terminations.items())),
        "engine_moves": len(engine_moves),
        "engine_moves_without_score": moves_without_score,
    }

    summary_md = summarize.build_summary(meta, results, completed)
    pgn_text = "\n\n".join(g["pgn"].strip() for g in games if g["pgn"]) + "\n"
    all_moves = [m for g in games for m in g["moves"]]
    log_header = [
        f"engine command: {' '.join(engine_cmd)}",
        f"opponent command: {' '.join(opponent_cmd)}",
        f"engine id: {names['engine']}",
        f"opponent id: {names['opponent']}",
    ]
    engine_log = "\n".join(log_header + log_lines + [line for g in games for line in g.get("log", [])]) + "\n"

    if args.no_record:
        print(summary_md)
        return 0

    position_entries = [
        (move, "*" if (g["forfeit"] or g["result"] is None) else g["result"])
        for g in games
        for move in g["moves"]
    ]
    index_row = {
        "run_name": run_name,
        "date": date_key,
        "engine_version": engine_version,
        "opponent": opponent_label,
        "games": len(completed),
        "score_pct": "" if results["score_pct"] is None else results["score_pct"],
        "elo_diff": "" if results["elo_diff"] is None else results["elo_diff"],
        "sprt_decision": sprt_block["decision"],
    }
    run_dir = record.record_run(
        root, run_name, meta, results, summary_md, pgn_text, all_moves, engine_log, position_entries, index_row
    )
    print(f"Recorded run: {run_dir}")
    print(summary_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
