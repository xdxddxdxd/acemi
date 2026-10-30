"""Polyglot writer and mini-book builder tests."""

import tempfile
import unittest
from pathlib import Path

import chess
import chess.polyglot

from engine.board import Board
from engine.book import PolyglotBook
from tools import bookgen, polyglot


class EncodeTests(unittest.TestCase):
    def test_normal_move_encoding(self) -> None:
        board = chess.Board()
        self.assertEqual(polyglot.encode_move(board, chess.Move.from_uci("e2e4")), 796)

    def test_castling_is_encoded_as_king_to_rook(self) -> None:
        board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        self.assertEqual(polyglot.encode_move(board, chess.Move.from_uci("e1g1")), 263)

    def test_promotion_is_encoded(self) -> None:
        board = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        self.assertEqual(polyglot.encode_move(board, chess.Move.from_uci("a7a8q")), 19512)


class FakeEvaluator:
    def multipv(self, board: chess.Board, depth: int) -> list[tuple[chess.Move, int]]:
        moves = [chess.Move.from_uci("e2e4"), chess.Move.from_uci("d2d4"), chess.Move.from_uci("a2a3")]
        return [(move, cp) for move, cp in zip(moves, (0, 20, 100)) if move in board.legal_moves]


class BuildTests(unittest.TestCase):
    def test_main_line_and_close_alternatives_are_kept(self) -> None:
        entries = bookgen.build_entries(
            [("Test", ["e2e4"])], FakeEvaluator(), max_plies=2, depth=2, cp_window=30
        )
        key = chess.polyglot.zobrist_hash(chess.Board())
        codes = entries[key]
        self.assertEqual(codes[polyglot.encode_move(chess.Board(), chess.Move.from_uci("e2e4"))], 10)
        self.assertGreaterEqual(len(codes), 2)  # at least one close alternative

    def test_far_alternatives_are_dropped(self) -> None:
        entries = bookgen.build_entries(
            [("Test", ["e2e4"])], FakeEvaluator(), max_plies=1, depth=2, cp_window=30
        )
        codes = entries[chess.polyglot.zobrist_hash(chess.Board())]
        self.assertEqual(len(codes), 2)  # e2e4 plus the 0/20 cp alternatives, not the 100 cp one

    def test_written_book_is_readable_by_the_engine(self) -> None:
        entries = bookgen.build_entries(
            [("Test", ["e2e4"])], FakeEvaluator(), max_plies=1, depth=2, cp_window=30
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.bin"
            polyglot.write_book(path, entries)
            book = PolyglotBook(path)
            move = book.find_move(Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"))
        self.assertIsNotNone(move)
        self.assertEqual(move.uci(), "e2e4")


if __name__ == "__main__":
    unittest.main()
