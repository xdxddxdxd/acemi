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
import shutil
import subprocess
import sys
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
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

from engine.board import Board as AcemiBoard  # noqa: E402
from engine.movegen import find_legal_move  # noqa: E402
from tools import elo as elo_tools  # noqa: E402
from tools import pairing  # noqa: E402
from tools import record, summarize  # noqa: E402
from tools import sprt as sprt_tools  # noqa: E402
from tools.uci_client import (  # noqa: E402
    EngineCrashed,
    EngineError,
    EngineSetupError,
    EngineTimeout,
    UciEngine,
)

SCHEMA_VERSION = record.SCHEMA_VERSION
BUILTIN_SET_NAME = "builtin-mini-8"
BUILTIN_OPENINGS = (
    ("Ruy Lopez", "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6"),
    ("Sicilian", "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6"),
    ("Queen's Gambit Declined", "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6"),
    ("King's Indian", "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7"),
    ("French", "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6"),
    ("Caro-Kann", "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4 c3e4 c8f5"),
    ("Reti", "g1f3 d7d5 g2g3 g8f6 f1g2 e7e6"),
    ("English", "c2c4 e7e5 b1c3 g8f6 g1f3 b8c6"),
)
STOCKFISH_CANDIDATES = ("/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish")
PGN_TERMINATION = {
    "timeout": "time forfeit",
    "illegal_move": "rules infraction",
    "crash": "abandoned",
}
OPENING_PLIES_MAX = 20
ENDGAME_MATERIAL_MAX = 26
PIECE_POINTS = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


@dataclass(frozen=True)
class Opening:
    name: str
    start_fen: str | None
    moves: tuple[str, ...]


# -- openings --------------------------------------------------------------


def builtin_openings() -> list[Opening]:
    return [
        Opening(name=f"{name}: {line}", start_fen=None, moves=tuple(line.split()))
        for name, line in BUILTIN_OPENINGS
    ]


def load_openings(path: Path) -> tuple[str, list[Opening]]:
    """Read an opening file: one FEN/EPD or one line of UCI moves per row.

    Blank lines and lines starting with ``#`` are skipped. Returns (set name, openings).
    """
    openings: list[Opening] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        tokens = text.split()
        if "/" in tokens[0]:
            if len(tokens) >= 6 and tokens[4].isdigit() and tokens[5].isdigit():
                fen = " ".join(tokens[:6])
            else:
                fen = " ".join(tokens[:4]) + " 0 1"
            try:
                chess.Board(fen)
            except ValueError as error:
                raise ValueError(f"{path}:{number}: invalid FEN ({error})") from error
            openings.append(Opening(name=text, start_fen=fen, moves=()))
        else:
            board = chess.Board()
            for token in tokens:
                try:
                    board.push_uci(token)
                except ValueError as error:
                    raise ValueError(f"{path}:{number}: illegal opening move {token!r}") from error
            openings.append(Opening(name=text, start_fen=None, moves=tuple(tokens)))
    if not openings:
        raise ValueError(f"{path}: no openings found")
    return path.stem, openings


# -- one game (runs in a worker process) ------------------------------------


def _start_engine(engine: UciEngine, options: list[list]) -> None:
    try:
        engine.start()
        for name, value, required in options:
            engine.set_option(name, value, required=required)
        engine.new_game()
    except EngineSetupError:
        raise
    except EngineError as error:
        raise EngineSetupError(f"{engine.label} failed during startup: {error}") from error


def _mirror_move(
    acemi_board: AcemiBoard | None, board: chess.Board, move: chess.Move, log: list[str]
) -> tuple[AcemiBoard | None, bool]:
    """Apply ``move`` to Acemi's board and compare with python-chess (already updated).

    Returns (board or None, disagreed). After a disagreement the Acemi board is
    dropped for the rest of the game and later records carry no Zobrist hash.
    """
    if acemi_board is None:
        return None, False
    try:
        acemi_board.make_move(find_legal_move(acemi_board, move.uci()))
    except ValueError as error:
        log.append(f"Acemi board rejected {move.uci()}: {error}")
        return None, True
    expected_fen = board.fen(en_passant="fen")
    if (
        acemi_board.to_fen() != expected_fen
        or acemi_board.zobrist_hash != acemi_board.compute_zobrist_hash()
    ):
        log.append(f"Acemi board disagrees with python-chess after {move.uci()}")
        return None, True
    return acemi_board, False


def _parse_legal(board: chess.Board, text: str) -> chess.Move | None:
    try:
        move = chess.Move.from_uci(text)
    except ValueError:
        return None
    return move if move in board.legal_moves else None


def _end_phase(board: chess.Board) -> str:
    plies = len(board.move_stack)
    if plies <= OPENING_PLIES_MAX:
        return "opening"
    material = 0
    for piece_type, points in PIECE_POINTS.items():
        for color in (chess.WHITE, chess.BLACK):
            material += points * len(board.pieces(piece_type, color))
    return "endgame" if material <= ENDGAME_MATERIAL_MAX else "middlegame"


def _engine_result(result: str, engine_is_white: bool) -> str:
    if result == "1/2-1/2":
        return "draw"
    if result == "1-0":
        return "win" if engine_is_white else "loss"
    if result == "0-1":
        return "loss" if engine_is_white else "win"
    return "aborted"


def _build_pgn(job: dict, board: chess.Board, result: str, termination: str) -> str:
    game = chess.pgn.Game.from_board(board)
    engine_is_white = job["engine_is_white"]
    game.headers["Event"] = job["event"]
    game.headers["Site"] = "kaggle-or-local"
    game.headers["Date"] = job["pgn_date"]
    game.headers["Round"] = str(job["game_no"] + 1)
    game.headers["White"] = job["engine_name"] if engine_is_white else job["opponent_name"]
    game.headers["Black"] = job["opponent_name"] if engine_is_white else job["engine_name"]
    game.headers["Result"] = result
    game.headers["Opening"] = job["opening"]["name"]
    game.headers["Termination"] = termination
    game.headers["MoveTimeMs"] = str(job["movetime_ms"])
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return game.accept(exporter)


def _play_moves(job: dict, engine: UciEngine, opponent: UciEngine, log: list[str]) -> dict:
    engine_is_white: bool = job["engine_is_white"]
    opening = job["opening"]
    board = chess.Board(opening["start_fen"]) if opening["start_fen"] else chess.Board()

    acemi_board: AcemiBoard | None
    try:
        acemi_board = AcemiBoard(board.fen())
    except ValueError as error:
        log.append(f"Acemi board rejected the start position: {error}")
        acemi_board = None
    disagreements = 0 if acemi_board is not None else 1

    for text in opening["moves"]:
        move = chess.Move.from_uci(text)
        board.push(move)
        acemi_board, disagreed = _mirror_move(acemi_board, board, move, log)
        disagreements += int(disagreed)

    root_fen = board.root().fen()
    moves_out: list[dict] = []
    forfeit: dict | None = None
    result = "*"
    termination = ""

    while True:
        outcome = board.outcome(claim_draw=True)
        if outcome is not None:
            result = outcome.result()
            termination = outcome.termination.name.lower()
            break
        if len(board.move_stack) >= job["max_plies"]:
            result, termination = "1/2-1/2", "max_plies"
            break

        mover_is_engine = (board.turn == chess.WHITE) == engine_is_white
        who = "engine" if mover_is_engine else "opponent"
        player = engine if mover_is_engine else opponent
        side = "white" if board.turn == chess.WHITE else "black"
        if acemi_board is not None:
            fen_before, hash_before = acemi_board.to_fen(), f"{acemi_board.zobrist_hash:016x}"
        else:
            fen_before, hash_before = board.fen(), None
        ply = len(board.move_stack) + 1

        command = f"position fen {root_fen}"
        if board.move_stack:
            command += " moves " + " ".join(m.uci() for m in board.move_stack)
        try:
            found = player.search(command, job["movetime_ms"], job["grace_ms"])
        except EngineTimeout as error:
            forfeit = {"who": who, "reason": "timeout"}
            log.append(f"{who} timed out at ply {ply}: {error}")
            break
        except EngineError as error:
            forfeit = {"who": who, "reason": "crash"}
            log.append(f"{who} failed at ply {ply}: {error}")
            break

        move = _parse_legal(board, found.bestmove)
        if move is None:
            forfeit = {"who": who, "reason": "illegal_move"}
            log.append(f"{who} played illegal move {found.bestmove!r} at ply {ply} in {fen_before}")
            break

        moves_out.append(
            {
                "schema_version": SCHEMA_VERSION,
                "game_no": job["game_no"] + 1,
                "ply": ply,
                "side": side,
                "player": who,
                "fen": fen_before,
                "zobrist_hash": hash_before,
                "move": move.uci(),
                "eval_cp": found.score_cp,
                "eval_mate": found.score_mate,
                "depth": found.depth,
                "nodes": found.nodes,
                "time_ms": found.elapsed_ms,
            }
        )
        board.push(move)
        acemi_board, disagreed = _mirror_move(acemi_board, board, move, log)
        disagreements += int(disagreed)

    if forfeit is not None:
        termination = forfeit["reason"]
        if forfeit["who"] == "engine":
            result = "0-1" if engine_is_white else "1-0"
        else:
            result = "*"  # Opponent failure: the game says nothing about Acemi.

    engine_result = _engine_result(result, engine_is_white)
    return {
        "game_no": job["game_no"] + 1,
        "pair_no": job["pair_no"],
        "opening_id": job["opening_id"],
        "opening": opening["name"],
        "engine_color": "white" if engine_is_white else "black",
        "result": None if result == "*" else result,
        "engine_result": engine_result,
        "termination": termination,
        "forfeit": forfeit,
        "plies": len(board.move_stack),
        "end_phase": _end_phase(board),
        "board_disagreements": disagreements,
        "pgn": _build_pgn(job, board, result, PGN_TERMINATION.get(termination, "normal")),
        "moves": moves_out,
    }


def play_game(job: dict) -> dict:
    """Play one game. Never raises: failures become aborted games or a fatal message."""
    log: list[str] = []
    engine = UciEngine(job["engine_cmd"], label="engine", cwd=job["engine_cwd"], log=log)
    opponent = UciEngine(job["opponent_cmd"], label="opponent", cwd=job["opponent_cwd"], log=log)
    try:
        _start_engine(engine, job["engine_options"])
        _start_engine(opponent, job["opponent_options"])
        game = _play_moves(job, engine, opponent, log)
    except EngineSetupError as error:
        return {"fatal": str(error), "game_no": job["game_no"] + 1}
    except Exception:  # noqa: BLE001 - one broken game must not stop the whole run
        log.append("Internal error:\n" + traceback.format_exc())
        game = {
            "game_no": job["game_no"] + 1,
            "pair_no": job["pair_no"],
            "opening_id": job["opening_id"],
            "opening": job["opening"]["name"],
            "engine_color": "white" if job["engine_is_white"] else "black",
            "result": None,
            "engine_result": "aborted",
            "termination": "internal_error",
            "forfeit": None,
            "plies": 0,
            "end_phase": "opening",
            "board_disagreements": 0,
            "pgn": "",
            "moves": [],
        }
    finally:
        engine.close()
        opponent.close()
    game["log"] = [f"[game {game['game_no']}] {line}" for line in log]
    return game


# -- run setup and aggregation ----------------------------------------------


def _split_name_version(raw: str) -> tuple[str, str]:
    parts = raw.split()
    if len(parts) >= 2 and parts[-1][:1].isdigit():
        return " ".join(parts[:-1]), parts[-1]
    return raw or "unknown", "unknown"


def _git_info(root: Path) -> dict:
    def run(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return done.stdout.strip()

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def _ram_mb() -> int | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as stream:
            for line in stream:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _find_stockfish(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    found = shutil.which("stockfish")
    if found:
        return found
    for candidate in STOCKFISH_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _split_command(text: str) -> list[str]:
    return shlex.split(text, posix=(os.name != "nt"))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--games", type=int, default=20, help="games to play (maximum with --sprt)")
    parser.add_argument("--movetime-ms", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=None, help="parallel games (default: cores - 1)")
    parser.add_argument("--uci-elo", type=int, default=None, help="Stockfish UCI_Elo (default 1320 for Stockfish)")
    parser.add_argument("--stockfish-path", default=None)
    parser.add_argument("--opponent-cmd", default=None, help="any UCI engine command instead of Stockfish")
    parser.add_argument("--opponent-cwd", default=None)
    parser.add_argument("--engine-cmd", default=None, help="engine under test (default: python -m engine)")
    parser.add_argument("--engine-cwd", default=None)
    parser.add_argument("--openings", default=None, help="opening file (FEN/EPD or UCI-move lines)")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--hash-mb", type=int, default=16)
    parser.add_argument("--max-plies", type=int, default=400)
    parser.add_argument("--grace-ms", type=int, default=1000, help="extra time allowed beyond movetime")
    parser.add_argument("--sprt", action="store_true", help="stop early when the SPRT decides")
    parser.add_argument("--elo0", type=float, default=0.0)
    parser.add_argument("--elo1", type=float, default=10.0)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--beta", type=float, default=0.05)
    parser.add_argument("--root", default=str(ROOT), help="repository root that receives data/")
    parser.add_argument("--no-record", action="store_true", help="print the summary, write nothing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
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

    # Preflight: start both engines once to read their names and validate options.
    log_lines: list[str] = []
    names: dict[str, str] = {}
    for label, command, cwd, options in (
        ("engine", engine_cmd, engine_cwd, base_engine_options),
        ("opponent", opponent_cmd, args.opponent_cwd, base_opponent_options),
    ):
        probe = UciEngine(command, label=label, cwd=cwd, log=log_lines)
        try:
            _start_engine(probe, options)
            names[label] = probe.name
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
    git = _git_info(ROOT)

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
            "opening_book": False,
        },
        "opponent": {"name": opponent_name, "version": opponent_version, "uci_elo": uci_elo},
        "opening_set": opening_set,
        "match_settings": {
            "games_requested": args.games,
            "concurrency": concurrency,
            "max_plies": args.max_plies,
            "timeout_grace_ms": args.grace_ms,
            "pairing": "colour_swapped_pairs",
        },
        "hardware": {
            "cpu_count": cores,
            "ram_mb": _ram_mb(),
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
