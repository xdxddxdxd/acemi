"""UCI protocol front end for Acemi.

Stage 4: ``go`` runs iterative negamax with quiescence; ``info depth`` is the
last completed depth. Supported limits: ``depth``, ``movetime``, ``nodes``,
the clock (``wtime``/``btime``/``winc``/``binc``/``movestogo``) and
``infinite``/``stop``. Infinite search runs in a worker thread and ``stop``
returns its latest result instead of starting a new search.
"""

from __future__ import annotations

import random
import sys
from threading import Event, Thread
from typing import TextIO

from engine import __version__
from engine.board import STARTING_FEN, WHITE, Board
from engine.eval.classic import FLAGS
from engine.movegen import find_legal_move
from engine.search import DEFAULT_DEPTH, MAX_DEPTH, Searcher, SearchResult

ENGINE_NAME = "Acemi"
ENGINE_AUTHOR = "xdxddxdxd"
NO_MOVE = "0000"
DEFAULT_SEED = 1
DEFAULT_HASH_MB = 16
OVERHEAD_MS = 30  # Reserved for process and pipe latency on every move.
DEFAULT_MOVES_TO_GO = 30
GO_NUMBER_KEYS = ("depth", "movetime", "nodes", "wtime", "btime", "winc", "binc", "movestogo")


def time_budget_ms(remaining_ms: int, increment_ms: int = 0, moves_to_go: int | None = None) -> int:
    """Milliseconds to spend on one move from the clock.

    An even share of the remaining time plus most of the increment, never more
    than half of what is left, minus a fixed overhead reserve; at least 1 ms.
    """
    moves = moves_to_go if moves_to_go and moves_to_go > 0 else DEFAULT_MOVES_TO_GO
    budget = remaining_ms // moves + (increment_ms * 3) // 4
    budget = min(budget, remaining_ms // 2)
    return max(budget - OVERHEAD_MS, 1)

OPTION_LINES = (
    "option name Hash type spin default 16 min 1 max 4096",
    "option name Threads type spin default 1 min 1 max 1",
    "option name Seed type spin default 1 min 0 max 2147483647",
    # Feature switches so one build can play against itself with a feature off (A/B tests).
    "option name NullMove type check default true",
    "option name LMR type check default true",
    "option name Killers type check default true",
    "option name PVS type check default false",
    "option name CheckExtension type check default false",
    # Stage 7 evaluation features (off until proven by a match).
    "option name EvalPassedPawns type check default false",
    "option name EvalPawnStructure type check default false",
    "option name EvalBishopPair type check default false",
    "option name EvalKingSafety type check default false",
    # A new iteration starts only if the time left is at least this percent of the last one.
    "option name NextIterationPct type spin default 150 min 50 max 500",
)
CHECK_OPTIONS = {
    "nullmove": "use_null_move",
    "lmr": "use_lmr",
    "killers": "use_killers",
    "pvs": "use_pvs",
    "checkextension": "use_check_extension",
}
EVAL_OPTIONS = {
    "evalpassedpawns": "passed_pawns",
    "evalpawnstructure": "pawn_structure",
    "evalbishoppair": "bishop_pair",
    "evalkingsafety": "king_safety",
}


class UciSession:
    """Line-oriented UCI state machine. ``handle_line`` returns the reply lines."""

    def __init__(self) -> None:
        self.board = Board(STARTING_FEN)
        self.seed = DEFAULT_SEED
        self.rng = random.Random(self.seed)  # Breaks ties between equal root moves.
        self.hash_mb = DEFAULT_HASH_MB
        self.searcher = Searcher(self.hash_mb)  # Keeps its transposition table between moves.
        self.threads = 1
        self.quit_requested = False
        self._infinite_thread: Thread | None = None
        self._infinite_stop: Event | None = None
        self._infinite_result: SearchResult | None = None

    def handle_line(self, line: str) -> list[str]:
        tokens = line.split()
        if not tokens:
            return []
        command, args = tokens[0], tokens[1:]

        if command == "uci":
            return [
                f"id name {ENGINE_NAME} {__version__}",
                f"id author {ENGINE_AUTHOR}",
                *OPTION_LINES,
                "uciok",
            ]
        if command == "isready":
            return ["readyok"]
        if command == "ucinewgame":
            self._cancel_infinite()
            self.board = Board(STARTING_FEN)
            self.rng = random.Random(self.seed)  # Same seed -> same game, every game.
            self.searcher.clear_tt()
            return []
        if command == "setoption":
            self._cancel_infinite()
            return self._set_option(args)
        if command == "position":
            self._cancel_infinite()
            return self._set_position(args)
        if command == "go":
            return self._go(args)
        if command == "stop":
            result = self._finish_infinite()
            return [] if result is None else self._format_result(result)
        if command == "quit":
            self._cancel_infinite()
            self.quit_requested = True
            return []
        return [f"info string Unknown command: {command}"]

    def _set_option(self, args: list[str]) -> list[str]:
        if not args or args[0] != "name":
            return ["info string setoption needs 'name <id> [value <x>]'"]
        if "value" in args:
            split = args.index("value")
            name_tokens, value_tokens = args[1:split], args[split + 1 :]
        else:
            name_tokens, value_tokens = args[1:], []
        name = " ".join(name_tokens).lower()
        value = " ".join(value_tokens)

        if name in EVAL_OPTIONS:
            text = value.strip().lower()
            if text not in ("true", "false"):
                return [f"info string Option {name} needs true or false"]
            setattr(FLAGS, EVAL_OPTIONS[name], text == "true")
            return []
        if name in CHECK_OPTIONS:
            text = value.strip().lower()
            if text not in ("true", "false"):
                return [f"info string Option {name} needs true or false"]
            setattr(self.searcher, CHECK_OPTIONS[name], text == "true")
            return []
        if name == "nextiterationpct":
            try:
                percent = int(value)
            except ValueError:
                return [f"info string Option {name} needs an integer value"]
            if not 50 <= percent <= 500:
                return [f"info string Option {name} must be between 50 and 500"]
            self.searcher.next_iteration_factor = percent / 100.0
            return []
        if name in ("hash", "threads", "seed"):
            try:
                number = int(value)
            except ValueError:
                return [f"info string Option {name} needs an integer value"]
            if name == "hash":
                self.hash_mb = number
                self.searcher.resize_tt(number)
            elif name == "threads":
                self.threads = number
            else:
                self.seed = number
                self.rng = random.Random(number)
            return []
        return [f"info string Unknown option: {' '.join(name_tokens)}"]

    def _set_position(self, args: list[str]) -> list[str]:
        try:
            if args and args[0] == "startpos":
                board = Board(STARTING_FEN)
                rest = args[1:]
            elif args and args[0] == "fen":
                if "moves" in args:
                    split = args.index("moves")
                    fen_tokens, rest = args[1:split], args[split:]
                else:
                    fen_tokens, rest = args[1:], []
                board = Board(" ".join(fen_tokens))
            else:
                raise ValueError("position needs 'startpos' or 'fen <fen>'")

            if rest:
                if rest[0] != "moves":
                    raise ValueError(f"unexpected token {rest[0]!r}")
                for text in rest[1:]:
                    board.make_move(find_legal_move(board, text))
        except ValueError as error:
            return [f"info string Invalid position command: {error}"]
        self.board = board
        return []

    def _go(self, args: list[str]) -> list[str]:
        if "infinite" in args:
            self._start_infinite()
            return []

        self._cancel_infinite()
        values: dict[str, int] = {}
        index = 0
        while index < len(args):
            token = args[index]
            if token in GO_NUMBER_KEYS and index + 1 < len(args):
                try:
                    values[token] = int(args[index + 1])
                except ValueError:
                    pass
                index += 2
            else:
                index += 1

        movetime_ms: int | None = None
        if "movetime" in values:
            movetime_ms = max(1, values["movetime"])
        else:
            white = self.board.side_to_move == WHITE
            clock_key, increment_key = ("wtime", "winc") if white else ("btime", "binc")
            if clock_key in values:
                movetime_ms = time_budget_ms(
                    max(0, values[clock_key]),
                    max(0, values.get(increment_key, 0)),
                    values.get("movestogo"),
                )

        if "depth" in values:
            depth = max(0, values["depth"])
        elif movetime_ms is not None:
            depth = MAX_DEPTH  # Time decides: iterate deeper until the budget is used.
        else:
            depth = DEFAULT_DEPTH
        nodes_limit = max(0, values["nodes"]) if "nodes" in values else None
        return self._run_search(depth=depth, movetime_ms=movetime_ms, nodes_limit=nodes_limit)

    def _start_infinite(self) -> None:
        self._cancel_infinite()
        stop_event = Event()
        self._infinite_stop = stop_event
        self._infinite_result = None
        self._infinite_thread = Thread(
            target=self._search_infinite,
            args=(stop_event,),
            name="acemi-search",
            daemon=True,
        )
        self._infinite_thread.start()

    def _search_infinite(self, stop_event: Event) -> None:
        self._infinite_result = self.searcher.search(
            self.board,
            depth=MAX_DEPTH,
            stop_event=stop_event,
            rng=self.rng,
        )

    def _finish_infinite(self) -> SearchResult | None:
        thread = self._infinite_thread
        stop_event = self._infinite_stop
        if thread is None or stop_event is None:
            return None
        stop_event.set()
        thread.join()
        self._infinite_thread = None
        self._infinite_stop = None
        result = self._infinite_result
        self._infinite_result = None
        return result

    def _cancel_infinite(self) -> None:
        self._finish_infinite()

    def _run_search(
        self,
        *,
        depth: int,
        movetime_ms: int | None,
        nodes_limit: int | None = None,
    ) -> list[str]:
        result = self.searcher.search(
            self.board,
            depth=depth,
            movetime_ms=movetime_ms,
            nodes_limit=nodes_limit,
            rng=self.rng,
        )
        return self._format_result(result)

    @staticmethod
    def _format_result(result: SearchResult) -> list[str]:
        info = f"info depth {result.depth}"
        if result.mate is not None:
            info += f" score mate {result.mate}"
        elif result.score is not None:
            info += f" score cp {result.score}"
        info += f" nodes {result.nodes} time {result.time_ms}"
        best_move = NO_MOVE if result.best_move is None else result.best_move.uci()
        # ``depth`` is the last finished iteration; the deepest started one (whose
        # partial result may have been played) is reported on an ``info string``.
        return [info, f"info string attempted_depth {result.attempted_depth}", f"bestmove {best_move}"]


def main(stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    session = UciSession()
    for raw_line in stdin:
        output = session.handle_line(raw_line)
        if output:
            stdout.write("\n".join(output) + "\n")
            stdout.flush()
        if session.quit_requested:
            break


if __name__ == "__main__":
    main()
