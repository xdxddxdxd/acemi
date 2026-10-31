"""The shipped Polyglot book must stay legal and match its seed list."""

import unittest
from pathlib import Path

from engine.board import Board
from engine.book import PolyglotBook, polyglot_hash
from engine.movegen import generate_legal_moves
from tools.bookgen import load_lines

ROOT = Path(__file__).resolve().parents[1]
BOOK_PATH = ROOT / "openings" / "book.bin"
SEED_PATH = ROOT / "openings" / "book_seeds.txt"
MAX_PLIES = 18


class ShippedBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.book = PolyglotBook(BOOK_PATH)
        cls.lines = load_lines(SEED_PATH)

    def test_seed_list_keeps_the_accepted_base(self) -> None:
        self.assertGreaterEqual(len(self.lines), 64)
        for name, moves in self.lines:
            with self.subTest(line=name):
                self.assertGreaterEqual(len(moves), 10)
                board = Board()
                for uci in moves[:MAX_PLIES]:
                    move = next((candidate for candidate in generate_legal_moves(board) if candidate.uci() == uci), None)
                    self.assertIsNotNone(move, f"{name}: illegal {uci}")
                    board.make_move(move)

    def test_every_book_move_is_legal_and_reachable(self) -> None:
        visited: set[int] = set()
        queue = [Board()]
        while queue:
            board = queue.pop()
            key = polyglot_hash(board)
            if key in visited:
                continue
            visited.add(key)
            raw_moves = self.book.entries.get(key)
            if not raw_moves:
                continue
            legal = {move.uci(): move for move in generate_legal_moves(board)}
            self.assertTrue(legal, "book entry at a terminal position")
            for code, _weight in raw_moves:
                decoded = self.book._decode_move(board, code)
                self.assertIn(decoded.uci() if decoded else None, legal)
                child = Board(board.to_fen())
                child.make_move(legal[decoded.uci()])
                queue.append(child)
        self.assertFalse(set(self.book.entries) - visited)

    def test_every_seed_position_up_to_book_depth_is_present(self) -> None:
        for name, moves in self.lines:
            with self.subTest(line=name):
                board = Board()
                played = moves[:MAX_PLIES]
                for ply, uci in enumerate(played):
                    self.assertIn(polyglot_hash(board), self.book.entries, f"{name}: missing ply {ply}")
                    move = next(candidate for candidate in generate_legal_moves(board) if candidate.uci() == uci)
                    board.make_move(move)
                if len(moves) < MAX_PLIES:
                    self.assertIn(polyglot_hash(board), self.book.entries, f"{name}: missing line end")

    def test_start_position_has_several_replies(self) -> None:
        self.assertGreaterEqual(len(self.book.entries[polyglot_hash(Board())]), 3)


if __name__ == "__main__":
    unittest.main()
