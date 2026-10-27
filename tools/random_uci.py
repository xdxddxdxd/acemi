"""Minimal UCI engine that plays seeded random legal moves.

Used as the Stage 3 gate opponent ("beat random 100/100"). It reuses the Acemi
board and move generator so legality matches the engine under test, but never
searches. Launch with::

    python tools/random_uci.py

or as a match opponent::

    python -m tools.match --opponent-cmd "python -u tools/random_uci.py" --games 100
"""

from __future__ import annotations

import random
import sys
from typing import TextIO

from engine.board import STARTING_FEN, Board
from engine.movegen import find_legal_move, generate_legal_moves

ENGINE_NAME = "AcemiRandom"
ENGINE_AUTHOR = "xdxddxdxd"
NO_MOVE = "0000"
DEFAULT_SEED = 1


class RandomUciSession:
    def __init__(self) -> None:
        self.board = Board(STARTING_FEN)
        self.seed = DEFAULT_SEED
        self.quit_requested = False

    def handle_line(self, line: str) -> list[str]:
        tokens = line.split()
        if not tokens:
            return []
        command, args = tokens[0], tokens[1:]

        if command == "uci":
            return [
                f"id name {ENGINE_NAME}",
                f"id author {ENGINE_AUTHOR}",
                "option name Seed type spin default 1 min 0 max 2147483647",
                "uciok",
            ]
        if command == "isready":
            return ["readyok"]
        if command == "ucinewgame":
            self.board = Board(STARTING_FEN)
            return []
        if command == "setoption":
            return self._set_option(args)
        if command == "position":
            return self._set_position(args)
        if command == "go":
            return [self._bestmove_line()]
        if command == "stop":
            return [self._bestmove_line()]
        if command == "quit":
            self.quit_requested = True
            return []
        return []

    def _set_option(self, args: list[str]) -> list[str]:
        if "name" not in args or "value" not in args:
            return []
        name_idx = args.index("name")
        value_idx = args.index("value")
        name = " ".join(args[name_idx + 1 : value_idx]).lower()
        value = " ".join(args[value_idx + 1 :])
        if name == "seed":
            try:
                self.seed = int(value)
            except ValueError:
                pass
        return []

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
                return []
            if rest and rest[0] == "moves":
                for text in rest[1:]:
                    board.make_move(find_legal_move(board, text))
            self.board = board
        except ValueError:
            pass
        return []

    def _bestmove_line(self) -> str:
        moves = list(generate_legal_moves(self.board))
        if not moves:
            return f"bestmove {NO_MOVE}"
        rng = random.Random(f"{self.seed}:{self.board.zobrist_hash}")
        return f"bestmove {rng.choice(moves).uci()}"


def main(stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    session = RandomUciSession()
    for raw_line in stdin:
        output = session.handle_line(raw_line)
        if output:
            stdout.write("\n".join(output) + "\n")
            stdout.flush()
        if session.quit_requested:
            break


if __name__ == "__main__":
    main()
