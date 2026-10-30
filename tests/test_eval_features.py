"""Stage 7 evaluation features: each is off by default, symmetric between colours, and switchable."""

import unittest

from engine.board import Board
from engine.eval.base import evaluate
from engine.eval.classic import FLAGS
from engine.uci import UciSession

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
# A lone passed pawn, and the same position with colours swapped.
PASSED_WHITE = "4k3/8/8/3P4/8/8/8/4K3 w - - 0 1"
PASSED_BLACK = "4k3/8/8/8/3p4/8/8/4K3 b - - 0 1"
# d5 and d7 block each other: neither pawn is passed.
BLOCKED = "4k3/3p4/8/3P4/8/8/8/4K3 w - - 0 1"


class FlagTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = FLAGS.passed_pawns
        FLAGS.passed_pawns = False

    def tearDown(self) -> None:
        FLAGS.passed_pawns = self._saved


class PassedPawnTests(FlagTestCase):
    def score(self, fen: str, on: bool) -> int:
        FLAGS.passed_pawns = on
        return evaluate(Board(fen))

    def test_off_by_default(self) -> None:
        self.assertFalse(FLAGS.passed_pawns)

    def test_start_position_stays_zero(self) -> None:
        self.assertEqual(self.score(START, True), 0)

    def test_passed_pawn_is_rewarded(self) -> None:
        self.assertGreater(self.score(PASSED_WHITE, True), self.score(PASSED_WHITE, False))

    def test_blocked_pawn_gets_no_bonus(self) -> None:
        self.assertEqual(self.score(BLOCKED, True), self.score(BLOCKED, False))

    def test_symmetric_between_colours(self) -> None:
        # PASSED_BLACK is PASSED_WHITE with colours swapped: same score for the side to move.
        self.assertEqual(self.score(PASSED_WHITE, True), self.score(PASSED_BLACK, True))
        self.assertEqual(self.score(PASSED_WHITE, False), self.score(PASSED_BLACK, False))

    def test_more_advanced_is_worth_more(self) -> None:
        low = self.score("4k3/8/8/8/8/3P4/8/4K3 w - - 0 1", True)
        high = self.score("4k3/8/3P4/8/8/8/8/4K3 w - - 0 1", True)
        self.assertGreater(high, low)

    def test_neighbouring_file_pawn_blocks(self) -> None:
        # Black pawn on e7 is ahead of the d5 pawn's neighbouring file: d5 is not passed.
        fen = "4k3/4p3/8/3P4/8/8/8/4K3 w - - 0 1"
        self.assertEqual(self.score(fen, True), self.score(fen, False))

    def test_pawn_beside_does_not_block(self) -> None:
        # Black pawn on e4 is behind d5, and White's e2 pawn stops it being passed itself:
        # only d5 (relative rank index 4) earns a bonus.
        from engine.eval.classic import _PASSED_EG, _PASSED_MG, _passed_pawn_bonus

        board = Board("4k3/8/8/3P4/4p3/8/4P3/4K3 w - - 0 1")
        self.assertEqual(_passed_pawn_bonus(board), (_PASSED_MG[4], _PASSED_EG[4]))


class UciSwitchTests(FlagTestCase):
    def test_option_is_declared_and_toggles(self) -> None:
        session = UciSession()
        self.assertIn("option name EvalPassedPawns type check default false", "\n".join(session.handle_line("uci")))
        self.assertEqual(session.handle_line("setoption name EvalPassedPawns value true"), [])
        self.assertTrue(FLAGS.passed_pawns)
        session.handle_line("setoption name EvalPassedPawns value false")
        self.assertFalse(FLAGS.passed_pawns)

    def test_bad_value_is_ignored(self) -> None:
        reply = UciSession().handle_line("setoption name EvalPassedPawns value maybe")
        self.assertTrue(reply and reply[0].startswith("info string"))
        self.assertFalse(FLAGS.passed_pawns)


if __name__ == "__main__":
    unittest.main()
