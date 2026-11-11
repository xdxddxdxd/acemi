"""Real search regressions: run these on Kaggle, never as a local smoke test."""

import unittest

from engine.board import Board
from engine.search import MATE_SCORE, Searcher


class QuiescenceSeeSearchTests(unittest.TestCase):
    def test_full_window_quiescence_scores_and_restoration(self):
        positions = (
            'k7/8/2p5/3r3p/6P1/8/8/K2Q4 w - - 0 1',
            '3r3k/8/8/3p4/3R4/8/8/K2R4 w - - 0 1',
            '7k/8/8/3pP3/3r4/8/8/K7 w - d6 0 1',
            'r6k/1P6/8/8/8/8/8/7K w - - 0 1',
            '7k/5Q2/6K1/8/8/8/8/8 b - - 0 1',  # stalemate
            '7k/6Q1/6K1/8/8/8/8/8 b - - 0 1',  # mate
        )
        for fen in positions:
            scores = []
            for enabled in (False, True):
                board = Board(fen)
                initial = board.to_fen(), board.zobrist_hash, list(board.position_hashes)
                searcher = Searcher(quiescence_see=enabled)
                scores.append(searcher._quiesce(board, -MATE_SCORE, MATE_SCORE, 0))
                self.assertEqual((board.to_fen(), board.zobrist_hash, board.position_hashes), initial)
            self.assertEqual(scores[0], scores[1], fen)

    def test_see_search_returns_legal_move_with_all_promotions_available(self):
        from engine.movegen import generate_legal_moves
        board = Board('r6k/1P6/8/8/8/8/8/7K w - - 0 1')
        legal = list(generate_legal_moves(board))
        self.assertEqual(len([m for m in legal if m.promotion is not None]), 8)
        result = Searcher(quiescence_see=True).search(board, depth=2)
        self.assertIn(result.best_move, legal)
