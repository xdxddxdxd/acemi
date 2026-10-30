"""Stage 7 evaluation features: each is off by default, symmetric between colours, and switchable."""

import unittest

from engine.board import Board
from engine.eval.base import evaluate
from engine.eval.classic import FLAGS, EvalFlags
from engine.uci import UciSession

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
# A lone passed pawn, and the same position with colours swapped.
PASSED_WHITE = "4k3/8/8/3P4/8/8/8/4K3 w - - 0 1"
PASSED_BLACK = "4k3/8/8/8/3p4/8/8/4K3 b - - 0 1"
# d5 and d7 block each other: neither pawn is passed.
BLOCKED = "4k3/3p4/8/3P4/8/8/8/4K3 w - - 0 1"


class FlagTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {name: getattr(FLAGS, name) for name in EvalFlags.__slots__}
        for name in EvalFlags.__slots__:
            setattr(FLAGS, name, False)

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            setattr(FLAGS, name, value)


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


class PawnStructureTests(FlagTestCase):
    # Black's a7/b7 pawns are connected, so any penalty below comes from White's pawns only.
    ISOLATED = "4k3/pp6/8/8/3P4/8/8/4K3 w - - 0 1"
    DOUBLED = "4k3/pp6/8/3P4/2PP4/8/8/4K3 w - - 0 1"
    BACKWARD = "4k3/pp6/8/2P5/3P4/8/8/4K3 w - - 0 1"
    # Mirror images of one another (same score for the side to move).
    WHITE_D4 = "4k3/8/8/8/3P4/8/8/4K3 w - - 0 1"
    BLACK_D5 = "4k3/8/8/3p4/8/8/8/4K3 b - - 0 1"

    def score(self, fen: str, on: bool) -> int:
        FLAGS.pawn_structure = on
        return evaluate(Board(fen))

    def test_off_by_default(self) -> None:
        self.assertFalse(FLAGS.pawn_structure)

    def test_start_position_stays_zero(self) -> None:
        self.assertEqual(self.score(START, True), 0)

    def test_isolated_pawn_is_penalised(self) -> None:
        from engine.eval.classic import _ISOLATED_EG, _ISOLATED_MG, _pawn_structure

        self.assertLess(self.score(self.ISOLATED, True), self.score(self.ISOLATED, False))
        self.assertEqual(_pawn_structure(Board(self.ISOLATED)), (-_ISOLATED_MG, -_ISOLATED_EG))

    def test_doubled_pawns_are_penalised_once_per_extra_pawn(self) -> None:
        from engine.eval.classic import _DOUBLED_EG, _DOUBLED_MG, _pawn_structure

        self.assertLess(self.score(self.DOUBLED, True), self.score(self.DOUBLED, False))
        self.assertEqual(_pawn_structure(Board(self.DOUBLED)), (-_DOUBLED_MG, -_DOUBLED_EG))

    def test_backward_pawn_is_penalised(self) -> None:
        from engine.eval.classic import _BACKWARD_EG, _BACKWARD_MG, _pawn_structure

        self.assertLess(self.score(self.BACKWARD, True), self.score(self.BACKWARD, False))
        self.assertEqual(_pawn_structure(Board(self.BACKWARD)), (-_BACKWARD_MG, -_BACKWARD_EG))

    def test_isolated_is_not_also_backward(self) -> None:
        from engine.eval.classic import _ISOLATED_EG, _ISOLATED_MG, _pawn_structure

        # A lone white pawn on the d file, no black pawns: isolated, not backward too.
        self.assertEqual(_pawn_structure(Board(self.WHITE_D4)), (-_ISOLATED_MG, -_ISOLATED_EG))

    def test_symmetric_between_colours(self) -> None:
        self.assertEqual(self.score(self.WHITE_D4, True), self.score(self.BLACK_D5, True))
        self.assertEqual(self.score(self.WHITE_D4, False), self.score(self.BLACK_D5, False))


class BishopPairTests(FlagTestCase):
    WHITE_PAIR = "2b1k3/8/8/8/8/8/8/2B1KB2 w - - 0 1"
    BLACK_PAIR = "2b1kb2/8/8/8/8/8/8/2B1K3 b - - 0 1"

    def score(self, fen: str, on: bool) -> int:
        FLAGS.bishop_pair = on
        return evaluate(Board(fen))

    def test_off_by_default(self) -> None:
        self.assertFalse(FLAGS.bishop_pair)

    def test_start_position_stays_zero(self) -> None:
        self.assertEqual(self.score(START, True), 0)

    def test_bishop_pair_is_rewarded(self) -> None:
        from engine.eval.classic import _BISHOP_PAIR_EG, _BISHOP_PAIR_MG, _bishop_pair_bonus

        self.assertGreater(self.score(self.WHITE_PAIR, True), self.score(self.WHITE_PAIR, False))
        self.assertEqual(_bishop_pair_bonus(Board(self.WHITE_PAIR)), (_BISHOP_PAIR_MG, _BISHOP_PAIR_EG))

    def test_single_bishop_gets_no_bonus(self) -> None:
        from engine.eval.classic import _bishop_pair_bonus

        self.assertEqual(_bishop_pair_bonus(Board("4k3/8/8/8/8/8/8/2B1K3 w - - 0 1")), (0, 0))

    def test_symmetric_between_colours(self) -> None:
        self.assertEqual(self.score(self.WHITE_PAIR, True), self.score(self.BLACK_PAIR, True))
        self.assertEqual(self.score(self.WHITE_PAIR, False), self.score(self.BLACK_PAIR, False))


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

    def test_new_options_toggle(self) -> None:
        session = UciSession()
        options = "\n".join(session.handle_line("uci"))
        for name, flag in (("EvalPawnStructure", "pawn_structure"), ("EvalBishopPair", "bishop_pair")):
            self.assertIn(f"option name {name} type check default false", options)
            self.assertEqual(session.handle_line(f"setoption name {name} value true"), [])
            self.assertTrue(getattr(FLAGS, flag))
            session.handle_line(f"setoption name {name} value false")
            self.assertFalse(getattr(FLAGS, flag))


if __name__ == "__main__":
    unittest.main()
