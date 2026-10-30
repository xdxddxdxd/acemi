"""A/B switches: UCI feature options and the match runner's option parsing (no engines)."""

import unittest

from engine.search import Searcher
from engine.uci import UciSession
from tools import summarize


def parse_assignments(items):
    # tools.match needs python-chess at import time; the parser is pure, so load it lazily.
    from tools.match import parse_option_assignments

    return parse_option_assignments(items)


class UciFeatureOptionTests(unittest.TestCase):
    def test_options_are_declared(self) -> None:
        text = "\n".join(UciSession().handle_line("uci"))
        for name in ("NullMove", "LMR", "Killers", "NextIterationPct"):
            self.assertIn(f"option name {name} ", text)

    def test_check_options_toggle_the_searcher(self) -> None:
        session = UciSession()
        for option, attribute in (("NullMove", "use_null_move"), ("LMR", "use_lmr"), ("Killers", "use_killers")):
            with self.subTest(option=option):
                self.assertTrue(getattr(session.searcher, attribute))
                self.assertEqual(session.handle_line(f"setoption name {option} value false"), [])
                self.assertFalse(getattr(session.searcher, attribute))
                session.handle_line(f"setoption name {option} value true")
                self.assertTrue(getattr(session.searcher, attribute))

    def test_bad_check_value_is_reported_and_ignored(self) -> None:
        session = UciSession()
        reply = session.handle_line("setoption name NullMove value maybe")
        self.assertTrue(reply and reply[0].startswith("info string"))
        self.assertTrue(session.searcher.use_null_move)

    def test_next_iteration_pct(self) -> None:
        session = UciSession()
        self.assertEqual(session.searcher.next_iteration_factor, 1.5)
        session.handle_line("setoption name NextIterationPct value 110")
        self.assertAlmostEqual(session.searcher.next_iteration_factor, 1.1)
        reply = session.handle_line("setoption name NextIterationPct value 5")
        self.assertTrue(reply and reply[0].startswith("info string"))
        self.assertAlmostEqual(session.searcher.next_iteration_factor, 1.1)

    def test_constructor_default_factor_is_unchanged(self) -> None:
        self.assertEqual(Searcher().next_iteration_factor, 1.5)

    def test_switched_off_features_change_the_search(self) -> None:
        from engine.board import Board

        fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
        on = Searcher(lmr=True).search(Board(fen), depth=4)
        off = Searcher(lmr=False).search(Board(fen), depth=4)
        self.assertNotEqual(on.nodes, off.nodes)


class OptionAssignmentTests(unittest.TestCase):
    def test_values_are_typed_and_required(self) -> None:
        self.assertEqual(
            parse_assignments(["NullMove=false", "Hash=32", "Name=abc", "X=TRUE"]),
            [["NullMove", False, True], ["Hash", 32, True], ["Name", "abc", True], ["X", True, True]],
        )

    def test_malformed_assignments_are_rejected(self) -> None:
        for item in ("NullMove", "=true", "NullMove="):
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    parse_assignments([item])

    def test_none_gives_no_options(self) -> None:
        self.assertEqual(parse_assignments(None), [])


class SummaryOptionLineTests(unittest.TestCase):
    def test_summary_names_the_extra_options(self) -> None:
        meta = {
            "run_name": "r",
            "engine_version": "0.6.2",
            "opening_set": "x",
            "engine_settings": {"move_time_ms": 500, "extra_options": {"NullMove": True}},
            "opponent": {"name": "Acemi", "version": "0.6.2", "uci_elo": None, "extra_options": {"NullMove": False}},
        }
        results = {
            "games": 0, "wins": 0, "draws": 0, "losses": 0, "score_pct": None, "elo_diff": None,
            "sprt": {"enabled": False}, "aborted_games": 0, "average_plies": None, "timeouts": 0,
            "illegal_moves": 0, "engine_crashes": 0, "board_disagreements": 0, "average_depth": None,
            "nodes_per_second": None,
        }
        text = summarize.build_summary(meta, results, [])
        self.assertIn("Extra UCI options: engine {'NullMove': True}; opponent {'NullMove': False}", text)


if __name__ == "__main__":
    unittest.main()
