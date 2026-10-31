"""Endgame mate evaluation for KBBK and KBNK (off by default)."""

import unittest

from engine.board import Board
from engine.eval.base import evaluate
from engine.eval.classic import EvalFlags, FLAGS, _endgame_mate_bonus
from engine.uci import UciSession

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
KBBK_EDGE = "4k3/8/8/8/8/8/8/2BBK3 w - - 0 1"
KBBK_CENTER = "8/8/8/4k3/8/8/8/2BBK3 w - - 0 1"
KBBK_MIRROR = "2bbk3/8/8/8/8/8/8/4K3 b - - 0 1"
KBNK = "4k3/8/8/8/8/8/8/2BNK3 w - - 0 1"
KQK = "4k3/8/8/8/8/8/8/3QK3 w - - 0 1"
KRK = "4k3/8/8/8/8/8/8/3RK3 w - - 0 1"
KPK = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"


class FlagTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {name: getattr(FLAGS, name) for name in EvalFlags.__slots__}
        for name in EvalFlags.__slots__:
            setattr(FLAGS, name, False)

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            setattr(FLAGS, name, value)


class EndgameMateTests(FlagTestCase):
    def test_off_by_default(self) -> None:
        self.assertFalse(FLAGS.endgame_mate)

    def test_start_position_stays_zero(self) -> None:
        FLAGS.endgame_mate = True
        self.assertEqual(evaluate(Board(START)), 0)

    def test_kbbk_bonus_is_positive_and_edge_is_stronger(self) -> None:
        FLAGS.endgame_mate = True
        edge = evaluate(Board(KBBK_EDGE))
        center = evaluate(Board(KBBK_CENTER))
        self.assertGreater(edge, evaluate(Board(KBBK_EDGE)) - 1)  # sanity, flag on
        self.assertGreater(_endgame_mate_bonus(Board(KBBK_EDGE))[1], 0)
        self.assertGreater(_endgame_mate_bonus(Board(KBBK_EDGE))[1], _endgame_mate_bonus(Board(KBBK_CENTER))[1])
        self.assertGreater(edge, center)

    def test_kbnk_bonus_is_positive(self) -> None:
        FLAGS.endgame_mate = True
        self.assertGreater(_endgame_mate_bonus(Board(KBNK))[1], 0)
        self.assertGreater(evaluate(Board(KBNK)), evaluate(Board(KBNK)) - 1)

    def test_same_colour_bishops_are_not_a_mating_side(self) -> None:
        # c1 and e3 are both dark squares: KBB with same-colour bishops is not a win.
        self.assertEqual(_endgame_mate_bonus(Board("4k3/8/8/8/8/4B3/8/2B1K3 w - - 0 1")), (0, 0))

    def test_simple_mates_are_not_touched(self) -> None:
        FLAGS.endgame_mate = True
        for fen in (KQK, KRK, KPK):
            with self.subTest(fen=fen):
                self.assertEqual(_endgame_mate_bonus(Board(fen)), (0, 0))

    def test_symmetric_between_colours(self) -> None:
        white = _endgame_mate_bonus(Board(KBBK_EDGE))[1]
        black = _endgame_mate_bonus(Board(KBBK_MIRROR))[1]
        self.assertEqual(white, -black)

    def test_uci_option_toggles(self) -> None:
        session = UciSession()
        self.assertIn("option name EvalEndgameMate type check default false", "\n".join(session.handle_line("uci")))
        self.assertFalse(FLAGS.endgame_mate)
        self.assertEqual(session.handle_line("setoption name EvalEndgameMate value true"), [])
        self.assertTrue(FLAGS.endgame_mate)


if __name__ == "__main__":
    unittest.main()
