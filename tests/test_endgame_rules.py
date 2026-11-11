"""Horizon terminal/promotion correctness. Real searches belong in Kaggle."""

import copy
import unittest
from unittest.mock import Mock, patch

import chess

from engine.board import Board
from engine.eval.base import evaluate
from engine.movegen import generate_legal_moves, generate_legal_moves_reference
from engine.search import MATE_SCORE, MAX_PLY, Searcher

STALEMATE = "7k/5P2/6K1/8/8/8/8/8 b - - 0 1"
MATE = "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"
UNDERPROMOTION = "8/k1P5/2K5/8/8/8/8/8 w - - 0 1"


def both_colors(fen):
    return (fen, chess.Board(fen).mirror().fen())


class EndgamePositionTests(unittest.TestCase):
    """Small legality checks only: no search or recursive tree walks."""

    def test_promotion_fixture_distinguishes_stalemate_from_rook_conversion(self):
        for fen in both_colors(UNDERPROMOTION):
            oracle = chess.Board(fen)
            self.assertTrue(oracle.is_valid())
            pawn = next(iter(oracle.pieces(chess.PAWN, oracle.turn)))
            choices = {m.promotion: m for m in oracle.legal_moves if m.from_square == pawn}
            queen, rook = oracle.copy(), oracle.copy()
            queen.push(choices[chess.QUEEN])
            rook.push(choices[chess.ROOK])
            self.assertTrue(queen.is_stalemate())
            self.assertFalse(rook.is_game_over())
            self.assertFalse(rook.is_check())

    def test_tactical_generator_matches_all_oracle_captures_and_promotions(self):
        fixtures = (UNDERPROMOTION, "3r4/k1P5/2K5/8/8/8/8/8 w - - 0 1",
                    "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1",
                    "8/8/8/KPp4r/8/8/8/7k w - c6 0 1")
        for original in fixtures:
            for fen in both_colors(original):
                with self.subTest(fen=fen):
                    oracle = chess.Board(fen)
                    self.assertTrue(oracle.is_valid())
                    expected = {m.uci() for m in oracle.legal_moves if oracle.is_capture(m) or m.promotion}
                    board = Board(fen)
                    before = copy.deepcopy(board.__dict__)
                    actual = list(generate_legal_moves(board, captures_only=True))
                    self.assertEqual({m.uci() for m in actual}, expected)
                    self.assertEqual(actual, list(generate_legal_moves_reference(board, captures_only=True)))
                    self.assertEqual(board.__dict__, before)

    def test_peeking_at_one_legal_move_restores_the_entire_board(self):
        for fen in both_colors(UNDERPROMOTION) + both_colors("4k3/8/8/8/8/8/8/4K2R b - - 0 1"):
            board = Board(fen)
            before = copy.deepcopy(board.__dict__)
            self.assertIsNotNone(next(generate_legal_moves(board, known_in_check=board.in_check()), None))
            self.assertEqual(board.__dict__, before)

    def test_material_draws_do_not_confuse_opposite_bishops_or_two_knights(self):
        # Same-colour bishops cannot mate. Opposite-colour bishops and KNNK
        # can reach a mate with cooperation, so must not be auto-adjudicated.
        fixtures = (
            ("7k/8/8/8/8/4B3/8/2B1K3 w - - 0 1", True),
            ("7k/8/8/8/8/8/8/2BBK3 w - - 0 1", False),
            ("7k/8/8/8/8/8/8/1N2K1N1 w - - 0 1", False),
        )
        for original, expected in fixtures:
            for fen in both_colors(original):
                self.assertEqual(chess.Board(fen).is_insufficient_material(), expected)
                self.assertEqual(Board(fen).is_insufficient_material(), expected)


class QuiescenceTerminalFlowTests(unittest.TestCase):
    """Mocked terminal flow; no real board, move generation or recursive search."""

    def board(self, in_check=False):
        return Mock(**{"is_fifty_move_draw.return_value": False,
                       "is_threefold_repetition.return_value": False,
                       "is_insufficient_material.return_value": False,
                       "in_check.return_value": in_check})

    def test_stalemate_precedes_stand_pat_beta_cutoff_and_ply_limit(self):
        for ply in (1, MAX_PLY):
            searcher, board = Searcher(), self.board()
            with patch("engine.search.generate_legal_moves", return_value=iter(())), \
                 patch("engine.search.evaluate", return_value=9999) as static:
                self.assertEqual(searcher._quiesce(board, -10, 0, ply), 0)
                static.assert_not_called()
            board.make_move.assert_not_called()

    def test_mate_precedes_the_ply_limit(self):
        searcher, board = Searcher(), self.board(in_check=True)
        with patch("engine.search.generate_legal_moves", return_value=iter(())), \
             patch("engine.search.evaluate") as static:
            self.assertEqual(searcher._quiesce(board, -MATE_SCORE, MATE_SCORE, MAX_PLY),
                             -MATE_SCORE + MAX_PLY)
            static.assert_not_called()

    def test_nonterminal_position_can_still_use_the_ply_limit(self):
        for in_check in (False, True):
            with self.subTest(in_check=in_check):
                searcher, board = Searcher(), self.board(in_check)
                with patch("engine.search.generate_legal_moves", return_value=iter((object(),))), \
                     patch("engine.search.evaluate", return_value=37):
                    self.assertEqual(searcher._quiesce(board, -100, 100, MAX_PLY), 37)
                board.make_move.assert_not_called()

    def test_stalemate_keeps_the_configured_contempt_policy(self):
        searcher, board = Searcher(), self.board()
        with patch("engine.search.generate_legal_moves", return_value=iter(())), \
             patch.object(searcher, "_draw_score", return_value=-15) as draw:
            self.assertEqual(searcher._quiesce(board, -100, 100, 1), -15)
            draw.assert_called_once_with(board)


class EndgameSearchRegressionTests(unittest.TestCase):
    """Actual horizon/root searches: run in Kaggle, not on the user's PC."""

    def test_stalemate_is_zero_at_the_horizon_for_both_colors_and_windows(self):
        for fen in both_colors(STALEMATE):
            for alpha, beta in ((-MATE_SCORE, MATE_SCORE), (0, 1), (-1000, -999)):
                with self.subTest(fen=fen, window=(alpha, beta)):
                    board = Board(fen)
                    before = copy.deepcopy(board.__dict__)
                    self.assertEqual(Searcher()._quiesce(board, alpha, beta, 1), 0)
                    self.assertEqual(Searcher()._negamax(board, 0, alpha, beta, 1), 0)
                    self.assertEqual(board.__dict__, before)

    def test_mate_and_stalemate_are_preserved_at_max_ply(self):
        for original, score in ((MATE, -MATE_SCORE + MAX_PLY), (STALEMATE, 0)):
            for fen in both_colors(original):
                self.assertEqual(Searcher()._quiesce(Board(fen), -MATE_SCORE, MATE_SCORE, MAX_PLY), score)

    def test_no_capture_does_not_mean_stalemate(self):
        for fen in both_colors("4k3/8/8/8/8/8/8/4K2R b - - 0 1"):
            board = Board(fen)
            self.assertEqual(Searcher()._quiesce(board, -MATE_SCORE, MATE_SCORE, 1), evaluate(board))
            self.assertNotEqual(evaluate(board), 0)

    def test_quiescence_sees_rook_underpromotion_instead_of_a_stalemating_queen(self):
        for fen in both_colors(UNDERPROMOTION):
            board = Board(fen)
            before = copy.deepcopy(board.__dict__)
            score = Searcher(hash_mb=0)._quiesce(board, -MATE_SCORE, MATE_SCORE, 1)
            self.assertGreater(score, 400)
            self.assertEqual(board.__dict__, before)

    def test_root_avoids_stalemate_by_promoting_to_rook(self):
        for fen in both_colors(UNDERPROMOTION):
            for hash_mb in (0, 1):
                with self.subTest(fen=fen, hash_mb=hash_mb):
                    searcher = Searcher(hash_mb=hash_mb)
                    board = Board(fen)
                    before = copy.deepcopy(board.__dict__)
                    for _ in range(2):  # Repeat with a warm table as well.
                        result = searcher.search(board, depth=1)
                        self.assertIsNotNone(result.best_move)
                        self.assertTrue(result.best_move.uci().endswith("r"))
                        self.assertGreater(result.score, 400)
                        self.assertEqual(board.__dict__, before)


if __name__ == "__main__":
    unittest.main()
