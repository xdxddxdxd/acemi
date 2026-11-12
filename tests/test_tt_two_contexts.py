"""Direct table and UCI fixtures only; no engine search or matches."""

import unittest

from engine.board import Board
from engine.search import Searcher, TT_EXACT
from engine.uci import UciSession
from tools.tt_stats import TTDiagnosticSearcher


def position(clock):
    return Board(f'7k/8/8/8/8/8/8/KQ6 w - - {clock} 1')


class TwoContextTableTests(unittest.TestCase):
    def test_equal_clocks_with_distinct_histories_stay_separate(self):
        from engine.movegen import find_legal_move
        board = Board()
        for uci in ('g1f3', 'g8f6', 'f3g1', 'f6g8'):
            board.make_move(find_legal_move(board, uci))
        fresh = Board(board.to_fen())
        s = Searcher(tt_two_contexts=True)
        s._store(board, 3, TT_EXACT, 100, None)
        s._store(fresh, 3, TT_EXACT, 200, None)
        self.assertEqual(s._probe(board)[0].score, 100)
        self.assertEqual(s._probe(fresh)[0].score, 200)

    def test_two_contexts_survive_and_scores_never_cross_histories(self):
        s = Searcher(tt_two_contexts=True)
        a, b, absent = position(0), position(20), position(40)
        s._store(a, 8, TT_EXACT, 800, None)
        s._store(b, 2, TT_EXACT, 200, None)
        self.assertEqual(s.tt_size, 2)
        self.assertEqual((s._probe(a)[0].score, s._probe(b)[0].score), (800, 200))
        self.assertIsNone(s._probe(absent)[0])

    def test_third_context_retains_deeper_old_entry(self):
        s = Searcher(tt_two_contexts=True)
        a, b, c = position(0), position(20), position(40)
        for board, depth in ((a, 8), (b, 2), (c, 3)):
            s._store(board, depth, TT_EXACT, depth, None)
        self.assertEqual(s.tt_size, 2)
        self.assertEqual(s._probe(a)[0].score, 8)
        self.assertEqual(s._probe(c)[0].score, 3)
        self.assertIsNone(s._probe(b)[0])

    def test_shallower_write_cannot_destroy_deep_secondary(self):
        s = Searcher(tt_two_contexts=True)
        a, b = position(0), position(20)
        s._store(a, 8, TT_EXACT, 800, None)
        s._store(b, 2, TT_EXACT, 200, None)
        s._store(a, 1, TT_EXACT, -1, None)
        self.assertEqual(s._probe(a)[0].score, 800)
        s._store(a, 9, TT_EXACT, 900, None)
        self.assertEqual(s._probe(a)[0].score, 900)
        self.assertEqual(s._probe(b)[0].score, 200)

    def test_total_entry_capacity_counts_both_slots(self):
        s = Searcher(tt_two_contexts=True)
        s._tt_max = 2
        s._store(position(0), 8, TT_EXACT, 8, None)
        s._store(position(20), 2, TT_EXACT, 2, None)
        self.assertEqual(s.tt_size, s.tt_capacity)
        other = Board('7k/8/8/8/8/8/1Q6/K7 w - - 0 1')
        s._store(other, 1, TT_EXACT, 1, None)
        self.assertEqual(s.tt_size, 1)
        self.assertFalse(s._tt_secondary)

    def test_null_move_does_not_read_or_write_either_score(self):
        board = Board()
        board.make_null_move()
        s = Searcher(tt_two_contexts=True)
        s._store(Board(board.to_fen()), 2, TT_EXACT, 7, None)
        before = s._tt.copy(), s._tt_secondary.copy()
        self.assertIsNone(s._probe(board)[0])
        s._store(board, 8, TT_EXACT, 99, None)
        self.assertEqual((s._tt, s._tt_secondary), before)

    def test_uci_default_is_enabled_and_toggle_and_resize_clear_both_tables(self):
        u = UciSession()
        self.assertTrue(u.searcher.use_tt_two_contexts)
        self.assertIn('option name TTTwoContexts type check default true', u.handle_line('uci'))
        self.assertEqual(u.handle_line('setoption name TTTwoContexts value true'), [])
        for clock in (0, 20):
            u.searcher._store(position(clock), 3, TT_EXACT, 7, None)
        self.assertEqual(u.searcher.tt_size, 2)
        self.assertEqual(u.handle_line('setoption name TTTwoContexts value false'), [])
        self.assertEqual(u.searcher.tt_size, 0)
        self.assertFalse(u.searcher._tt_secondary)
        u.handle_line('setoption name TTTwoContexts value true')
        for clock in (0, 20):
            u.searcher._store(position(clock), 3, TT_EXACT, 7, None)
        u.searcher.resize_tt(1)
        self.assertEqual(u.searcher.tt_size, 0)

    def test_diagnostics_recognize_secondary_cutoffs(self):
        s = TTDiagnosticSearcher(tt_two_contexts=True)
        s._store(position(0), 8, TT_EXACT, 8, None)
        s._store(position(20), 2, TT_EXACT, 2, None)
        s._tt_window = (3, -10, 10, 0)
        s._probe(position(0))
        stats = s.snapshot_tt_stats()
        self.assertEqual(stats['second_slot_additions'], 1)
        self.assertEqual(stats['second_slot_cutoffs'], 1)
        self.assertEqual(stats['context_rejected'], 0)

    def test_instrumented_pair_replacement_and_capacity_match_plain(self):
        a, b = Searcher(tt_two_contexts=True), TTDiagnosticSearcher(tt_two_contexts=True)
        a._tt_max = b._tt_max = 2
        for clock, depth in ((0, 8), (20, 2), (40, 3), (0, 1), (0, 9)):
            for s in (a, b):
                s._store(position(clock), depth, TT_EXACT, depth, None)
            self.assertEqual((a._tt, a._tt_secondary), (b._tt, b._tt_secondary))
            b.snapshot_tt_stats()
        other = Board('7k/8/8/8/8/8/1Q6/K7 w - - 0 1')
        for s in (a, b):
            s._store(other, 1, TT_EXACT, 1, None)
        self.assertEqual((a._tt, a._tt_secondary), (b._tt, b._tt_secondary))
        self.assertEqual(b.snapshot_tt_stats()['capacity_clears'], 1)
