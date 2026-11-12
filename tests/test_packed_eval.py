"""Short evaluation-only regressions: no searches or game simulations."""
import itertools
import unittest

from engine.board import Board, STARTING_FEN
from engine.eval import classic as ev
from engine.uci import UciSession


class PackedEvalTests(unittest.TestCase):
    def assert_base(self, board):
        mg = eg = phase = 0
        for square, piece in enumerate(board.squares):
            if square & 0x88 or not piece:
                continue
            sign = 1 if piece > 0 else -1
            mg += sign * ev._MG_VALUES[piece][square]
            eg += sign * ev._EG_VALUES[piece][square]
            phase += ev.PHASE_WEIGHT[abs(piece)]
        self.assertEqual(ev._packed_base(board), (mg, eg, phase))

    def test_signed_lanes_and_phase_at_every_piece_square(self):
        for piece in ev._MG_VALUES:
            for square in range(128):
                if square & 0x88:
                    continue
                board = Board('7k/8/8/8/8/8/8/K7 w - - 0 1')
                if board.squares[square]:
                    continue
                board._put_piece(piece, square)
                self.assert_base(board)

    def test_dense_promotions_negative_scores_and_all_other_flags(self):
        fens = [STARTING_FEN, '7k/8/8/8/8/8/8/K7 b - - 99 90',
                '7k/2pp4/8/3P4/4P3/8/8/KB1B4 w - - 0 1',
                'qqqqqqqk/qqqqqqqq/qqqqqqqq/qqqqqqqq/qqqqqqqq/qqqqqqqq/qqqqqqqq/Kqqqqqqq b - - 0 1',
                'KQQQQQQQ/QQQQQQQQ/QQQQQQQQ/QQQQQQQQ/QQQQQQQQ/QQQQQQQQ/QQQQQQQQ/QQQQQQQk w - - 0 1']
        others = [name for name in ev.EvalFlags.__slots__ if name != 'packed_base']
        for fen in fens:
            board = Board(fen)
            self.assert_base(board)
            before = board.to_fen(), board.zobrist_hash, list(board.position_hashes)
            for values in itertools.product((False, True), repeat=len(others)):
                flags = ev.EvalFlags()
                for name, value in zip(others, values):
                    setattr(flags, name, value)
                original = ev.evaluate_classic(board, flags)
                flags.packed_base = True
                self.assertEqual(ev.evaluate_classic(board, flags), original)
            self.assertEqual((board.to_fen(), board.zobrist_hash, board.position_hashes), before)

    def test_uci_default_and_configuration_invalidation(self):
        u = UciSession()
        self.assertTrue(u.searcher.use_tt_two_contexts)
        self.assertTrue(u.eval_flags.packed_base)
        self.assertIn('option name EvalPackedBase type check default true', u.handle_line('uci'))
        from engine.search import TT_EXACT
        u.searcher._store(u.board, 3, TT_EXACT, 7, None)
        self.assertEqual(u.handle_line('setoption name EvalPackedBase value false'), [])
        self.assertFalse(u.eval_flags.packed_base)
        self.assertEqual(u.searcher.tt_size, 0)
        u.handle_line('setoption name EvalPackedBase value true')
        self.assertTrue(u.eval_flags.packed_base)
