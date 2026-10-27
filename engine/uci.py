"""UCI protocol front end for Acemi.

Stage 2 scope: protocol handling only. There is no search or evaluation yet, so
``go`` answers with a seeded random legal move. This placeholder exists so the
match tooling can be exercised end to end; its playing strength says nothing
about the real engine. Stage 3 replaces ``UciSession._bestmove_line``.

No ``info`` lines are printed because no depth, node count, or score is
actually measured. The match runner records such fields as null (not measured).
"""

from __future__ import annotations

import random
import sys
from typing import TextIO

from engine import __version__
from engine.board import STARTING_FEN, Board
from engine.movegen import find_legal_move, generate_legal_moves

ENGINE_NAME = "Acemi"
ENGINE_AUTHOR = "xdxddxdxd"
NO_MOVE = "0000"
DEFAULT_SEED = 1
DEFAULT_HASH_MB = 16

OPTION_LINES = (
    "option name Hash type spin default 16 min 1 max 4096",
    "option name Threads type spin default 1 min 1 max 1",
    "option name Seed type spin default 1 min 0 max 2147483647",
)


class UciSession:
    """Line-oriented UCI state machine. ``handle_line`` returns the reply lines."""

    def __init__(self) -> None:
        self.board = Board(STARTING_FEN)
        self.seed = DEFAULT_SEED
        self.hash_mb = DEFAULT_HASH_MB  # Accepted for GUI compatibility; no table exists yet.
        self.threads = 1
        self.quit_requested = False
        self._pending_infinite = False

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
            self.board = Board(STARTING_FEN)
            self._pending_infinite = False
            return []
        if command == "setoption":
            return self._set_option(args)
        if command == "position":
            return self._set_position(args)
        if command == "go":
            return self._go(args)
        if command == "stop":
            if self._pending_infinite:
                self._pending_infinite = False
                return [self._bestmove_line()]
            return []
        if command == "quit":
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

        if name in ("hash", "threads", "seed"):
            try:
                number = int(value)
            except ValueError:
                return [f"info string Option {name} needs an integer value"]
            if name == "hash":
                self.hash_mb = number
            elif name == "threads":
                self.threads = number
            else:
                self.seed = number
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
        # Search limits (movetime, depth, nodes, clocks) are ignored: the
        # placeholder answers instantly. Real time management arrives in Stage 4.
        if "infinite" in args:
            self._pending_infinite = True
            return []
        return [self._bestmove_line()]

    def _bestmove_line(self) -> str:
        moves = list(generate_legal_moves(self.board))
        if not moves:
            return f"bestmove {NO_MOVE}"
        # Seeded by option value and position, so a given seed always makes the
        # same choice in the same position regardless of call history.
        rng = random.Random(f"{self.seed}:{self.board.zobrist_hash}")
        return f"bestmove {rng.choice(moves).uci()}"


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
