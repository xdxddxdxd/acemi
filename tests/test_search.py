"""Stage 3 evaluation and search tests (no external engines)."""

import unittest

from engine.board import QUEEN, Board
from engine.eval.base import evaluate
from engine.eval.classic import PIECE_VALUE
from engine.movegen import generate_legal_moves
from engine.search import MATE_SCORE, search


class EvalTests(unittest.TestCase):
    def test_starting_position_is_equal(self) -> None:
        self.assertEqual(evaluate(Board()), 0)

    def test_white_up_a_queen_is_positive(self) -> None:
        board = Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1")
        self.assertEqual(evaluate(board), PIECE_VALUE[QUEEN])

    def test_side_to_move_perspective(self) -> None:
        board = Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR b KQkq - 0 1")
        self.assertEqual(evaluate(board), -PIECE_VALUE[QUEEN])


class SearchTests(unittest.TestCase):
    def test_search_returns_legal_move(self) -> None:
        board = Board()
        result = search(board, depth=2)
        self.assertIsNotNone(result.best_move)
        assert result.best_move is not None
        legal = {m.uci() for m in generate_legal_moves(Board())}
        self.assertIn(result.best_move.uci(), legal)
        self.assertGreater(result.nodes, 0)

    def test_rook_takes_hanging_queen(self) -> None:
        board = Board("4k3/8/8/8/3q4/8/8/R3K3 w Q - 0 1")
        result = search(board, depth=1)
        self.assertIsNotNone(result.best_move)
        assert result.best_move is not None
        self.assertEqual(result.best_move.uci(), "a1d4")
        self.assertGreaterEqual(result.score, PIECE_VALUE[QUEEN] - 50)

    def test_finds_mate_in_one(self) -> None:
        board = Board("6k1/5ppp/8/8/8/8/5PPP/4Q1K1 w - - 0 1")
        result = search(board, depth=2)
        self.assertIsNotNone(result.best_move)
        assert result.best_move is not None
        self.assertEqual(result.best_move.uci(), "e1e8")
        self.assertIsNotNone(result.mate)
        assert result.mate is not None
        self.assertGreater(result.mate, 0)
        self.assertGreater(result.score, MATE_SCORE - 100)

    def test_checkmate_position_has_no_move(self) -> None:
        board = Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        result = search(board, depth=1)
        self.assertIsNone(result.best_move)
        self.assertLess(result.score, 0)

    def test_stalemate_is_draw(self) -> None:
        # Black king on h8, white king on g6, white pawn on f7: stalemate.
        board = Board("7k/5P2/6K1/8/8/8/8/8 b - - 0 1")
        result = search(board, depth=1)
        self.assertIsNone(result.best_move)
        self.assertEqual(result.score, 0)

    def test_search_is_deterministic(self) -> None:
        first = search(Board(), depth=2)
        second = search(Board(), depth=2)
        assert first.best_move is not None and second.best_move is not None
        self.assertEqual(first.best_move.uci(), second.best_move.uci())
        self.assertEqual(first.score, second.score)


if __name__ == "__main__":
    unittest.main()
