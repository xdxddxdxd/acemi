"""UCI protocol front end for Acemi.

Stage 4: ``go`` runs iterative negamax with quiescence; ``info depth`` is the
last completed depth. Supported limits: ``depth``, ``movetime``, ``nodes``,
the clock (``wtime``/``btime``/``winc``/``binc``/``movestogo``) and
``infinite``/``stop``. All searches run in a worker, keeping the protocol input
loop responsive. A finite search publishes its result when finished; an infinite
search waits for ``stop``. Direct sessions without an output callback retain the
synchronous finite-search API used by embedders and in-process tests.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from typing import Callable, TextIO

from engine import __version__
from engine.board import STARTING_FEN, WHITE, Board
from engine.book import PolyglotBook
from engine.eval.classic import EvalFlags
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
    "option name LateMovePruning type check default false",
    "option name QuiescenceSEE type check default false",
    "option name TTTwoContexts type check default true",
    "option name OwnBook type check default false",
    "option name BookFile type string default openings/book.bin",
    # Stage 7 evaluation features (off until proven by a match).
    "option name EvalPassedPawns type check default false",
    "option name EvalPawnStructure type check default false",
    "option name EvalBishopPair type check default false",
    "option name EvalKingSafety type check default false",
    "option name EvalEndgameMate type check default false",
    "option name EvalPackedBase type check default false",
    # A new iteration starts only if the time left is at least this percent of the last one.
    "option name NextIterationPct type spin default 150 min 50 max 500",
    # Penalise draws only when the root side is clearly ahead (0 = off).
    "option name Contempt type spin default 0 min 0 max 200",
)
CHECK_OPTIONS = {
    "nullmove": "use_null_move",
    "lmr": "use_lmr",
    "killers": "use_killers",
    "pvs": "use_pvs",
    "checkextension": "use_check_extension",
    "latemovepruning": "use_lmp",
    "quiescencesee": "use_quiescence_see",
    "tttwocontexts": "use_tt_two_contexts",
}
EVAL_OPTIONS = {
    "evalpassedpawns": "passed_pawns",
    "evalpawnstructure": "pawn_structure",
    "evalbishoppair": "bishop_pair",
    "evalkingsafety": "king_safety",
    "evalendgamemate": "endgame_mate",
    "evalpackedbase": "packed_base",
}

SPIN_LIMITS = {
    "hash": (1, 4096),
    "threads": (1, 1),
    "seed": (0, 2147483647),
    "nextiterationpct": (50, 500),
    "contempt": (0, 200),
}


@dataclass
class _SearchJob:
    stop: Event
    infinite: bool
    thread: Thread | None = None
    result: SearchResult | None = None
    error: Exception | None = None
    cancelled: bool = False
    output_sent: bool = False
    lock: Lock = field(default_factory=Lock)


class UciSession:
    """Line-oriented UCI state machine.

    Immediate replies come from ``handle_line``. With ``on_output`` supplied,
    finite searches additionally publish their result from the worker. Without
    it, finite ``go`` calls wait and return the result as before.
    """

    def __init__(self, on_output: Callable[[list[str]], None] | None = None) -> None:
        self.board = Board(STARTING_FEN)
        self.seed = DEFAULT_SEED
        self.rng = random.Random(self.seed)  # Breaks ties between equal root moves.
        self.hash_mb = DEFAULT_HASH_MB
        self.eval_flags = EvalFlags()
        self.searcher = Searcher(self.hash_mb, eval_flags=self.eval_flags, tt_two_contexts=True)
        self.threads = 1
        self.use_book = False
        self.book: PolyglotBook | None = None
        self.book_path = "openings/book.bin"
        self.quit_requested = False
        self._on_output = on_output
        self._search_job: _SearchJob | None = None

    @property
    def searching(self) -> bool:
        job = self._search_job
        return job is not None and job.thread is not None and job.thread.is_alive()

    def close(self) -> None:
        """Stop outstanding work without publishing an obsolete result."""
        self._cancel_search()

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
            self._cancel_search()
            self.board = Board(STARTING_FEN)
            self.rng = random.Random(self.seed)  # Same seed -> same game, every game.
            self.searcher.clear_tt()
            return []
        if command == "setoption":
            self._cancel_search()
            return self._set_option(args)
        if command == "position":
            self._cancel_search()
            return self._set_position(args)
        if command == "go":
            return self._go(args)
        if command == "stop":
            return self._finish_search(stop=True)
        if command == "quit":
            self._cancel_search()
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

        if name == "bookfile":
            path = value.strip()
            if not path:
                self.book = None
                return []
            try:
                self.book = PolyglotBook(path)
                self.book_path = path
                return []
            except (OSError, ValueError) as error:
                self.book = None
                return [f"info string Book file error: {error}"]
        if name == "ownbook":
            text = value.strip().lower()
            if text not in ("true", "false"):
                return [f"info string Option {name} needs true or false"]
            self.use_book = text == "true"
            if self.use_book and self.book is None:
                try:
                    self.book = PolyglotBook(self.book_path)
                except (OSError, ValueError) as error:
                    return [f"info string Book file error: {error}"]
            return []
        if name in EVAL_OPTIONS:
            text = value.strip().lower()
            if text not in ("true", "false"):
                return [f"info string Option {name} needs true or false"]
            setattr(self.eval_flags, EVAL_OPTIONS[name], text == "true")
            self.searcher.sync_configuration()
            return []
        if name in CHECK_OPTIONS:
            text = value.strip().lower()
            if text not in ("true", "false"):
                return [f"info string Option {name} needs true or false"]
            setattr(self.searcher, CHECK_OPTIONS[name], text == "true")
            self.searcher.sync_configuration()
            return []
        if name in SPIN_LIMITS:
            try:
                number = int(value)
            except ValueError:
                return [f"info string Option {name} needs an integer value"]
            minimum, maximum = SPIN_LIMITS[name]
            if not minimum <= number <= maximum:
                return [f"info string Option {name} must be between {minimum} and {maximum}"]
            if name == "hash":
                if self.hash_mb != number:
                    self.hash_mb = number
                    self.searcher.resize_tt(number)
            elif name == "threads":
                self.threads = number
            elif name == "seed":
                self.seed = number
                self.rng = random.Random(number)
            elif name == "nextiterationpct":
                self.searcher.next_iteration_factor = number / 100.0
            else:  # contempt
                self.searcher.contempt = number
                self.searcher.sync_configuration()
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
        self._cancel_search()
        if "infinite" in args:
            self._start_search(depth=MAX_DEPTH, movetime_ms=None, infinite=True)
            return []

        if self.use_book and self.book is not None and len(self.board.undo_stack) < 24:
            move = self.book.find_move(self.board, self.rng)
            if move is not None:
                return [f"info string book move {move.uci()}", f"bestmove {move.uci()}"]
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
        self._start_search(depth=depth, movetime_ms=movetime_ms, nodes_limit=nodes_limit)
        return [] if self._on_output is not None else self._finish_search(stop=False)

    def _start_search(
        self,
        *,
        depth: int,
        movetime_ms: int | None,
        nodes_limit: int | None = None,
        infinite: bool = False,
    ) -> None:
        job = _SearchJob(stop=Event(), infinite=infinite)
        self._search_job = job
        job.thread = Thread(
            target=self._search_worker,
            args=(job, self.board, depth, movetime_ms, nodes_limit),
            name="acemi-search",
            daemon=True,
        )
        job.thread.start()

    def _search_worker(
        self,
        job: _SearchJob,
        board: Board,
        depth: int,
        movetime_ms: int | None,
        nodes_limit: int | None,
    ) -> None:
        try:
            job.result = self.searcher.search(
                board,
                depth=depth,
                movetime_ms=movetime_ms,
                nodes_limit=nodes_limit,
                stop_event=job.stop,
                rng=self.rng,
            )
        except Exception as error:
            # Keep a worker failure visible to both protocol and direct callers.
            job.error = error
        if self._on_output is not None and not job.infinite:
            lines = self._take_output(job)
            if lines:
                self._on_output(lines)

    def _take_output(self, job: _SearchJob) -> list[str]:
        with job.lock:
            if job.cancelled or job.output_sent:
                return []
            if job.error is not None:
                job.output_sent = True
                if self._on_output is None:
                    raise job.error
                detail = f"{type(job.error).__name__}: {job.error}".replace("\n", " ").replace("\r", " ")
                return [f"info string Search failed: {detail}", f"bestmove {NO_MOVE}"]
            if job.result is None:
                return []
            job.output_sent = True
            return self._format_result(job.result)

    def _finish_search(self, *, stop: bool) -> list[str]:
        job = self._search_job
        if job is None:
            return []
        if stop:
            job.stop.set()
        if job.thread is not None:
            job.thread.join()
        self._search_job = None
        return self._take_output(job)

    def _cancel_search(self) -> None:
        job = self._search_job
        if job is None:
            return
        with job.lock:
            job.cancelled = True
        job.stop.set()
        # Never change the board, options or RNG while the worker still uses them.
        # Also finish any in-flight output before processing the next position.
        if job.thread is not None:
            job.thread.join()
        self._search_job = None

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
    output_lock = Lock()

    def emit(lines: list[str]) -> None:
        if lines:
            with output_lock:
                stdout.write("\n".join(lines) + "\n")
                stdout.flush()

    session = UciSession(on_output=emit)
    try:
        for raw_line in stdin:
            emit(session.handle_line(raw_line))
            if session.quit_requested:
                break
    finally:
        # EOF and quit both release the search worker.
        session.close()


if __name__ == "__main__":
    main()
