"""Contempt: only penalise draws when the root side is ahead."""

import unittest

from engine.board import Board
from engine.search import Searcher
from engine.uci import UciSession

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
WHITE_AHEAD = "4k3/8/8/8/8/8/8/3QK3 w - - 0 1"
WHITE_AHEAD_BLACK_TO_MOVE = "4k3/8/8/8/8/8/8/3QK3 b - - 0 1"
BLACK_AHEAD = "4k3/8/8/8/8/8/8/3qK3 b - - 0 1"


class ContemptTests(unittest.TestCase):
    def test_default_is_zero(self) -> None:
        self.assertEqual(Searcher().contempt, 0)

    def test_root_ahead_penalises_draw(self) -> None:
        searcher = Searcher(contempt=15)
        searcher._root_color = 1
        self.assertEqual(searcher._draw_score(Board(WHITE_AHEAD)), -15)

    def test_opponent_to_move_draw_is_good_for_root(self) -> None:
        searcher = Searcher(contempt=15)
        searcher._root_color = 1
        self.assertEqual(searcher._draw_score(Board(WHITE_AHEAD_BLACK_TO_MOVE)), 15)

    def test_root_behind_keeps_draw_score(self) -> None:
        searcher = Searcher(contempt=15)
        searcher._root_color = 1
        self.assertEqual(searcher._draw_score(Board(BLACK_AHEAD)), 0)

    def test_zero_contempt_and_missing_root_are_safe(self) -> None:
        self.assertEqual(Searcher(contempt=0)._draw_score(Board(WHITE_AHEAD)), 0)
        self.assertEqual(Searcher(contempt=15)._draw_score(Board(WHITE_AHEAD)), 0)

    def test_uci_option_toggles(self) -> None:
        session = UciSession()
        self.assertIn("option name Contempt type spin default 0", "\n".join(session.handle_line("uci")))
        self.assertEqual(session.handle_line("setoption name Contempt value 15"), [])
        self.assertEqual(session.searcher.contempt, 15)
        reply = session.handle_line("setoption name Contempt value 500")
        self.assertTrue(reply and reply[0].startswith("info string"))

    def test_search_default_benchmark_is_unchanged(self) -> None:
        # Contempt 0 must not change the draw score.
        searcher = Searcher()
        searcher._root_color = 1
        self.assertEqual(searcher._draw_score(Board(WHITE_AHEAD)), 0)


if __name__ == "__main__":
    unittest.main()
