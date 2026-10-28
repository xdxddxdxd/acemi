"""Stage 3 evaluation and search tests (no external engines)."""

import random
import unittest
from unittest.mock import patch

from engine.board import QUEEN, ROOK, Board
from engine.eval.base import evaluate
from engine.eval.classic import PIECE_VALUE
from engine.movegen import generate_legal_moves
from engine.search import MATE_SCORE, search


class EvalTests(unittest.TestCase):
    def test_starting_position_is_equal(self) -> None:
        self.assertEqual(evaluate(Board()), 0)

    def test_white_up_a_queen_is_positive(self) -> None:
        # Black is missing its queen (rank 8: rnb1kbnr).
        board = Board("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        # Material plus a small piece-square term (the missing queen sat on d8).
        self.assertAlmostEqual(evaluate(board), PIECE_VALUE[QUEEN], delta=30)

    def test_side_to_move_perspective(self) -> None:
        # Same imbalance, black to move: black is down a queen -> negative.
        board = Board("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1")
        self.assertAlmostEqual(evaluate(board), -PIECE_VALUE[QUEEN], delta=30)


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
        # Queen on the a-file so the rook on a1 can capture along the file.
        # After RxQ the side to move is up a rook (~500 cp).
        board = Board("4k3/8/8/8/q7/8/8/R3K3 w Q - 0 1")
        result = search(board, depth=1)
        self.assertIsNotNone(result.best_move)
        assert result.best_move is not None
        self.assertEqual(result.best_move.uci(), "a1a4")
        self.assertGreaterEqual(result.score, PIECE_VALUE[ROOK] - 50)

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
        # Black king g8, white queen g7, white king g6: vertical mate.
        board = Board("6k1/6Q1/6K1/8/8/8/8/8 b - - 0 1")
        result = search(board, depth=1)
        self.assertIsNone(result.best_move)
        self.assertLess(result.score, 0)

    def test_stalemate_is_draw(self) -> None:
        # Black king h8, white king g6, white pawn f7: stalemate (not check).
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


    def test_reported_depth_is_last_completed_iteration(self) -> None:
        result = search(Board(), depth=2)
        self.assertEqual(result.depth, 2)

    def test_time_limit_returns_legal_move_with_honest_depth(self) -> None:
        # 1 ms cannot finish depth 6 from the start position.
        result = search(Board(), depth=6, movetime_ms=1)
        self.assertIsNotNone(result.best_move)
        assert result.best_move is not None
        legal = {m.uci() for m in generate_legal_moves(Board())}
        self.assertIn(result.best_move.uci(), legal)
        self.assertLess(result.depth, 6)

    def test_zero_time_still_returns_a_legal_move_without_deep_search(self) -> None:
        # Time checks run every 256 nodes, so a trivial first iteration may still
        # finish; what matters is a legal move and no further iterations.
        result = search(Board(), depth=6, movetime_ms=0)
        self.assertIsNotNone(result.best_move)
        assert result.best_move is not None
        legal = {m.uci() for m in generate_legal_moves(Board())}
        self.assertIn(result.best_move.uci(), legal)
        self.assertLessEqual(result.depth, 1)

    def test_ties_are_broken_by_seeded_rng(self) -> None:
        # A constant evaluation makes every quiet root move tie exactly.
        with patch("engine.search.evaluate", return_value=0):
            chosen = {
                search(Board(), depth=1, rng=random.Random(seed)).best_move.uci()
                for seed in range(30)
            }
        self.assertGreater(len(chosen), 1)

    def test_same_rng_seed_gives_same_tie_break(self) -> None:
        first = search(Board(), depth=1, rng=random.Random(5)).best_move
        second = search(Board(), depth=1, rng=random.Random(5)).best_move
        assert first is not None and second is not None
        self.assertEqual(first.uci(), second.uci())

    def test_tie_break_never_picks_a_worse_move(self) -> None:
        # Only a1a4 wins the queen; no seed may choose another move.
        for seed in range(10):
            result = search(Board("4k3/8/8/8/q7/8/8/R3K3 w Q - 0 1"), depth=1, rng=random.Random(seed))
            assert result.best_move is not None
            self.assertEqual(result.best_move.uci(), "a1a4")


if __name__ == "__main__":
    unittest.main()
