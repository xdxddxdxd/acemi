"""Late move pruning: skip late quiet moves at depth 1, off by default."""

import unittest

from engine.board import Board
from engine.search import Searcher
from engine.uci import UciSession

QUIET_MIDDLEGAME = "r2q1rk1/ppp2ppp/2np1n2/2b1p3/2B1P1b1/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 8"
MATE_IN_TWO = "1k6/8/8/1K6/1Q6/8/8/8 w - - 0 1"


class LateMovePruningTests(unittest.TestCase):
    def test_default_is_off(self) -> None:
        self.assertFalse(Searcher().use_lmp)

    def test_reduces_nodes_on_a_quiet_position(self) -> None:
        on = Searcher(lmp=True).search(Board(QUIET_MIDDLEGAME), depth=3)
        off = Searcher(lmp=False).search(Board(QUIET_MIDDLEGAME), depth=3)
        self.assertLess(on.nodes, off.nodes)
        self.assertIsNotNone(on.best_move)

    def test_still_finds_the_forced_mate(self) -> None:
        result = Searcher(lmp=True, check_extension=True).search(Board(MATE_IN_TWO), depth=2)
        self.assertEqual(result.best_move.uci(), "b5c6")
        self.assertEqual(result.mate, 2)

    def test_uci_option_toggles_the_searcher(self) -> None:
        session = UciSession()
        self.assertIn("option name LateMovePruning type check default false", "\n".join(session.handle_line("uci")))
        self.assertFalse(session.searcher.use_lmp)
        self.assertEqual(session.handle_line("setoption name LateMovePruning value true"), [])
        self.assertTrue(session.searcher.use_lmp)
        reply = session.handle_line("setoption name LateMovePruning value maybe")
        self.assertTrue(reply and reply[0].startswith("info string"))


if __name__ == "__main__":
    unittest.main()
