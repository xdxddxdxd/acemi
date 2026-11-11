"""Bounded exchange calculations and option checks; no engine search/process."""

import copy
import unittest
from unittest.mock import patch

from engine.board import Board
from engine.movegen import find_legal_move
from engine.search import Searcher, TT_EXACT, order_moves
from engine.see import static_exchange
from engine.uci import UciSession

CASES = (
    ('free pawn', '7k/8/8/3p4/4P3/8/8/K7 w - - 0 1', 'e4d5', 100),
    ('pawn trade', '7k/8/2p5/3p4/4P3/8/8/K7 w - - 0 1', 'e4d5', 0),
    ('queen lost', '7k/8/2p5/3p4/8/8/8/K2Q4 w - - 0 1', 'd1d5', -800),
    ('rook x-ray', '3r3k/8/8/3p4/3R4/8/8/K2R4 w - - 0 1', 'd4d5', 100),
    ('pinned pawn', '4k3/8/4p3/3p4/2B5/8/8/K3R3 w - - 0 1', 'c4d5', 100),
    ('unsafe king recapture', '8/8/4k3/3p4/2P5/8/8/K2R4 w - - 0 1', 'd1d5', 100),
    ('safe king recapture', '8/8/4k3/3p4/8/8/8/K2R4 w - - 0 1', 'd1d5', -400),
    ('en passant opens rook', '7k/8/8/3pP3/3r4/8/8/K7 w - d6 0 1', 'e5d6', 0),
    ('queen promotion', '8/P6k/8/8/8/8/8/7K w - - 0 1', 'a7a8q', 800),
    ('rook promotion', '8/P6k/8/8/8/8/8/7K w - - 0 1', 'a7a8r', 400),
    ('bishop promotion', '8/P6k/8/8/8/8/8/7K w - - 0 1', 'a7a8b', 230),
    ('knight promotion', '8/P6k/8/8/8/8/8/7K w - - 0 1', 'a7a8n', 220),
    ('capture promotion', 'r6k/1P6/8/8/8/8/8/7K w - - 0 1', 'b7a8q', 1300),
    ('recapture promotes', 'R7/8/7k/8/8/8/1p6/r6K w - - 0 1', 'a8a1', -800),
    ('black queen lost', 'k7/8/8/4q3/3P4/2P5/8/7K b - - 0 1', 'e5d4', -800),
)


class ExchangeTests(unittest.TestCase):
    def test_exchange_values_and_complete_board_immutability(self):
        for name, fen, uci, expected in CASES:
            with self.subTest(name=name):
                board = Board(fen)
                move = find_legal_move(board, uci)
                before = copy.deepcopy(vars(board))
                self.assertEqual(static_exchange(board, move), expected)
                self.assertEqual(vars(board), before)

    def test_ordering_demotes_losing_capture_without_removing_it(self):
        board = Board('k7/8/2p5/3r3p/6P1/8/8/K2Q4 w - - 0 1')
        moves = [find_legal_move(board, uci) for uci in ('d1d5', 'g4h5')]
        original = moves[:]
        Searcher(quiescence_see=True)._order_quiescence(board, moves, False)
        self.assertEqual(moves[0].uci(), 'g4h5')
        self.assertCountEqual(moves, original)

    def test_disabled_and_check_evasions_keep_legacy_order_without_see(self):
        board = Board('k7/8/2p5/3r3p/6P1/8/8/K2Q4 w - - 0 1')
        for enabled, in_check in ((False, False), (True, True)):
            moves = [find_legal_move(board, uci) for uci in ('g4h5', 'd1d5')]
            expected = moves[:]
            order_moves(board, expected)
            with patch('engine.search.static_exchange', side_effect=AssertionError('SEE called')):
                Searcher(quiescence_see=enabled)._order_quiescence(board, moves, in_check)
            self.assertEqual(moves, expected)

    def test_one_move_does_not_pay_for_see(self):
        board = Board(CASES[0][1])
        moves = [find_legal_move(board, CASES[0][2])]
        with patch('engine.search.static_exchange', side_effect=AssertionError('SEE called')):
            Searcher(quiescence_see=True)._order_quiescence(board, moves, False)

    def test_uci_is_opt_in_and_invalidates_table_on_toggle(self):
        session = UciSession()
        self.assertIn('option name QuiescenceSEE type check default false', session.handle_line('uci'))
        self.assertFalse(session.searcher.use_quiescence_see)
        session.searcher._store(session.board, 1, TT_EXACT, 7, None)
        self.assertGreater(session.searcher.tt_size, 0)
        self.assertEqual(session.handle_line('setoption name QuiescenceSEE value true'), [])
        self.assertTrue(session.searcher.use_quiescence_see)
        self.assertEqual(session.searcher.tt_size, 0)
        self.assertTrue(session.handle_line('setoption name QuiescenceSEE value maybe'))
        self.assertTrue(session.searcher.use_quiescence_see)
