"""Real search/oracle regressions; run only in the Kaggle suite."""

import functools
import random
import unittest
from unittest.mock import patch

from engine.board import Board
from engine.search import Searcher
from tests import test_tt_context as legacy
from tools.tt_diagnostics import _signature
from tools.tt_stats import TTDiagnosticSearcher


class TwoContextDrawRegressions(legacy.TTDrawRegressionTests):
    def setUp(self):
        replacement = functools.partial(Searcher, tt_two_contexts=True)
        patcher = patch.object(legacy, 'Searcher', replacement)
        patcher.start()
        self.addCleanup(patcher.stop)


class TwoContextSearchTests(unittest.TestCase):
    def test_scores_match_tt_disabled_oracle_without_selective_pruning(self):
        for fen in ('7k/8/8/8/8/8/8/KQ6 w - - 0 1',
                    '7k/8/8/3p4/4P3/8/8/K7 w - - 0 1',
                    'r6k/1P6/8/8/8/8/8/7K w - - 0 1'):
            oracle = Searcher(hash_mb=0, null_move=False, lmr=False).search(Board(fen), depth=2)
            pair = Searcher(tt_two_contexts=True, null_move=False, lmr=False)
            self.assertEqual(pair.search(Board(fen), depth=2).score, oracle.score)
            self.assertEqual(pair.search(Board(fen), depth=2).score, oracle.score)

    def test_instrumented_and_normal_pair_tables_agree(self):
        board = Board()
        plain = Searcher(tt_two_contexts=True)
        measured = TTDiagnosticSearcher(tt_two_contexts=True)
        a = plain.search(board, depth=64, nodes_limit=600, rng=random.Random(7))
        b = measured.search(board, depth=64, nodes_limit=600, rng=random.Random(7))
        self.assertEqual(_signature(a), _signature(b))
        self.assertEqual(plain._tt, measured._tt)
        self.assertEqual(plain._tt_secondary, measured._tt_secondary)
        measured.snapshot_tt_stats()
