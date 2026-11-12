"""Real instrumented/plain search equivalence: Kaggle suite only."""

import random
import unittest

from engine.board import Board
from engine.movegen import find_legal_move
from engine.search import Searcher
from tools.tt_diagnostics import _signature
from tools.tt_stats import TTDiagnosticSearcher


class TTInstrumentedSearchTests(unittest.TestCase):
    def test_instrumentation_preserves_node_limited_cold_and_warm_searches(self):
        board = Board()
        plain, measured = Searcher(), TTDiagnosticSearcher()
        rngs = random.Random(7), random.Random(7)
        for uci in ('g1f3', 'g8f6', 'd2d4', 'd7d5'):
            before = board.to_fen(), board.zobrist_hash, tuple(board.position_hashes)
            measured.reset_tt_stats()
            a = plain.search(board, depth=64, nodes_limit=300, rng=rngs[0])
            b = measured.search(board, depth=64, nodes_limit=300, rng=rngs[1])
            self.assertEqual(_signature(a), _signature(b))
            self.assertEqual(plain._tt, measured._tt)
            self.assertEqual(before, (board.to_fen(), board.zobrist_hash, tuple(board.position_hashes)))
            measured.snapshot_tt_stats()
            board.make_move(find_legal_move(board, uci))
