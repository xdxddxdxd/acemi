"""One match worker: UCI lifecycle, independent arbitration and per-game records."""

from __future__ import annotations

import traceback

import chess
import chess.pgn

from engine.board import Board as AcemiBoard
from engine.movegen import find_legal_move
from tools import record
from tools.uci_client import EngineError, EngineSetupError, EngineTimeout, UciEngine

SCHEMA_VERSION = record.SCHEMA_VERSION


PGN_TERMINATION = {
    "timeout": "time forfeit",
    "illegal_move": "rules infraction",
    "crash": "abandoned",
}

OPENING_PLIES_MAX = 20

ENDGAME_MATERIAL_MAX = 26

PIECE_POINTS = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}

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

def book_settings(engine: UciEngine, options: list[list]) -> dict:
    """Record configured OwnBook/BookFile, using advertised defaults and the last override.

    This describes the setting, not whether a particular game had a book hit.
    None means that the engine did not advertise the option.
    """
    effective = {name.lower(): option.default for name, option in engine.options.items()}
    for name, value, _ in options:
        if name.lower() in effective:
            effective[name.lower()] = value
    raw = effective.get("ownbook")
    enabled = {"true": True, "false": False}.get(str(raw).lower())
    book_file = effective.get("bookfile")
    return {"opening_book": enabled, "book_file": None if book_file is None else str(book_file)}

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
                "search_time_ms": found.search_time_ms,
                "attempted_depth": found.attempted_depth,
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
