"""Check extension: a checked node searches one ply deeper, once per line."""

import unittest

from engine.board import Board
from engine.search import Searcher
from engine.uci import UciSession

# 1.Kc6! is a quiet discovered check; every Black reply is met by mate in one.
MATE_IN_TWO = "1k6/8/8/1K6/1Q6/8/8/8 w - - 0 1"
KEY_MOVE = "b5c6"


class CheckExtensionTests(unittest.TestCase):
    def test_extension_finds_the_mate_two_plies_deeper(self) -> None:
        off = Searcher(check_extension=False).search(Board(MATE_IN_TWO), depth=2)
        on = Searcher(check_extension=True).search(Board(MATE_IN_TWO), depth=2)
        self.assertEqual(off.best_move.uci(), KEY_MOVE)
        self.assertIsNone(off.mate)
        self.assertEqual(on.best_move.uci(), KEY_MOVE)
        self.assertEqual(on.mate, 2)

    def test_many_checks_still_terminate(self) -> None:
        result = Searcher(check_extension=True).search(
            Board("6k1/5ppp/8/8/8/8/5PPP/3Q2K1 w - - 0 1"), depth=4
        )
        self.assertIsNotNone(result.best_move)
        self.assertLess(result.nodes, 1_000_000)

    def test_uci_option_toggles_the_searcher(self) -> None:
        session = UciSession()
        self.assertIn("option name CheckExtension type check default false", "\n".join(session.handle_line("uci")))
        self.assertFalse(session.searcher.use_check_extension)
        self.assertEqual(session.handle_line("setoption name CheckExtension value true"), [])
        self.assertTrue(session.searcher.use_check_extension)
        reply = session.handle_line("setoption name CheckExtension value maybe")
        self.assertTrue(reply and reply[0].startswith("info string"))

    def test_default_is_off(self) -> None:
        self.assertFalse(Searcher().use_check_extension)


if __name__ == "__main__":
    unittest.main()
