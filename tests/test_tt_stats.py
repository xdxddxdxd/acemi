"""Counters using direct table operations only: no recursive search or engines."""

import unittest

from engine.board import Board
from engine.movegen import find_legal_move
from engine.search import Searcher, TT_EXACT, TT_LOWER, TT_UPPER
from tools.tt_stats import TTDiagnosticSearcher, add_stats, empty_stats


class TTCounterTests(unittest.TestCase):
    def test_miss_context_depth_and_each_cutoff_reason(self):
        s = TTDiagnosticSearcher()
        board = Board('7k/8/8/8/8/8/8/KQ6 w - - 0 1')
        move = find_legal_move(board, 'b1b2')
        self.assertEqual(s._probe(board), (None, None))
        for flag, score, reason in ((TT_EXACT, 7, 'cutoff_exact'), (TT_LOWER, 50, 'cutoff_lower'),
                                    (TT_UPPER, -50, 'cutoff_upper')):
            s._store(board, 3, flag, score, move)
            s._tt_window = (2, -10, 10, 0)
            self.assertIsNotNone(s._probe(board)[0])
            self.assertEqual(s.tt_stats[reason], 1)
        s._tt_window = (4, -10, 10, 0)
        s._probe(board)
        s._store(board, 3, TT_LOWER, 0, move)
        s._tt_window = (2, -10, 10, 0)
        s._probe(board)
        late = Board('7k/8/8/8/8/8/8/KQ6 w - - 98 1')
        self.assertEqual(s._probe(late), (None, move))
        stats = s.snapshot_tt_stats()
        self.assertEqual(stats['too_shallow'], 1)
        self.assertEqual(stats['bound_no_cutoff'], 1)
        self.assertEqual(stats['context_rejected'], 1)
        self.assertEqual(stats['clock_mismatch'], 1)

    def test_same_clock_history_rejection_is_separate_from_clock(self):
        board = Board()
        for uci in ('g1f3', 'g8f6', 'f3g1', 'f6g8'):
            board.make_move(find_legal_move(board, uci))
        fresh = Board(board.to_fen())
        s = TTDiagnosticSearcher()
        s._store(fresh, 2, TT_EXACT, 0, None)
        s._probe(board)
        stats = s.snapshot_tt_stats()
        self.assertEqual(stats['same_clock_history_mismatch'], 1)
        self.assertEqual(stats['clock_mismatch'], 0)

    def test_null_and_disabled_stores_leave_table_unchanged(self):
        s = TTDiagnosticSearcher()
        board = Board()
        board.make_null_move()
        s._store(board, 2, TT_EXACT, 0, None)
        self.assertEqual(s.snapshot_tt_stats()['store_null'], 1)
        self.assertEqual(s.tt_size, 0)
        board.unmake_null_move()
        disabled = TTDiagnosticSearcher(hash_mb=0)
        disabled._store(board, 2, TT_EXACT, 0, None)
        self.assertEqual(disabled.snapshot_tt_stats()['store_disabled'], 1)

    def test_real_entry_is_rejected_in_synthetic_null_subtree(self):
        board = Board()
        board.make_null_move()
        s = TTDiagnosticSearcher()
        s._store(Board(board.to_fen()), 2, TT_EXACT, 7, None)
        before = s._tt.copy()
        self.assertEqual(s._probe(board), (None, None))
        self.assertEqual(s._tt, before)
        stats = s.snapshot_tt_stats()
        self.assertEqual((stats['hits'], stats['null_rejected'], stats['context_rejected']), (1, 1, 0))

    def test_capacity_and_depth_preference_match_production(self):
        plain, measured = Searcher(), TTDiagnosticSearcher()
        for s in (plain, measured):
            s._tt_max = 2
        for fen in ('7k/8/8/8/8/8/8/KQ6 w - - 0 1',
                    '7k/8/8/8/8/8/1Q6/K7 w - - 0 1',
                    '7k/8/8/8/8/8/2Q5/K7 w - - 0 1'):
            board = Board(fen)
            for s in (plain, measured):
                s._store(board, 3, TT_EXACT, 7, None)
                s._store(board, 1, TT_EXACT, 8, None)
            self.assertEqual(plain._tt, measured._tt)
        stats = measured.snapshot_tt_stats()
        self.assertEqual(stats['capacity_clears'], 1)
        self.assertEqual(stats['capacity_entries_discarded'], 2)
        self.assertEqual(stats['deeper_preserved'], 3)
        measured.reset_tt_stats()
        self.assertEqual(measured.tt_size, 1)
        measured.clear_tt()
        self.assertEqual(measured.snapshot_tt_stats()['explicit_entries_discarded'], 1)

    def test_aggregation_takes_maxima_instead_of_summing_them(self):
        a, b = empty_stats(), empty_stats()
        a['probes'], a['max_occupancy'] = 4, 8
        b['probes'], b['max_occupancy'] = 3, 5
        add_stats(a, b)
        self.assertEqual((a['probes'], a['max_occupancy']), (7, 8))
