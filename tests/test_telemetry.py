"""Telemetry: scoreless info lines, attempted depth, and summary lines (no engines)."""

import unittest

from engine.board import Board
from engine.search import search
from engine.uci import UciSession
from tools.summarize import _telemetry_lines
from tools.uci_client import parse_attempted_depth, parse_info_line


class ParseInfoLineTests(unittest.TestCase):
    def test_scored_line_keeps_depth_nodes_time_and_score(self) -> None:
        line = "info depth 6 seldepth 9 score cp 31 nodes 1500 nps 5000 time 300 pv e2e4 e7e5"
        self.assertEqual(parse_info_line(line), {"depth": 6, "cp": 31, "nodes": 1500, "time": 300})

    def test_mate_score(self) -> None:
        self.assertEqual(parse_info_line("info depth 3 score mate -2 nodes 40")["mate"], -2)

    def test_scoreless_line_with_depth_and_nodes_is_recorded(self) -> None:
        # What Acemi sends when it is stopped before finishing depth 1.
        self.assertEqual(
            parse_info_line("info depth 0 nodes 12 time 200"), {"depth": 0, "nodes": 12, "time": 200}
        )

    def test_progress_bound_and_string_lines_are_ignored(self) -> None:
        for line in (
            "info depth 14 currmove e2e4 currmovenumber 1",
            "info depth 10 score cp 20 lowerbound nodes 100",
            "info depth 10 score cp 20 upperbound nodes 100",
            "info string NNUE evaluation using nn.nnue",
            "info nps 1000",
            "bestmove e2e4",
        ):
            with self.subTest(line=line):
                self.assertIsNone(parse_info_line(line))

    def test_attempted_depth_line(self) -> None:
        self.assertEqual(parse_attempted_depth("info string attempted_depth 5"), 5)
        self.assertIsNone(parse_attempted_depth("info string something else"))
        self.assertIsNone(parse_attempted_depth("info depth 5 nodes 3"))


class AttemptedDepthTests(unittest.TestCase):
    def test_finished_search_attempted_equals_completed(self) -> None:
        result = search(Board(), depth=2)
        self.assertEqual((result.depth, result.attempted_depth), (2, 2))

    def test_cut_search_reports_the_unfinished_iteration(self) -> None:
        result = search(Board(), depth=8, nodes_limit=400)
        self.assertGreater(result.attempted_depth, result.depth)

    def test_uci_reports_attempted_depth_before_bestmove(self) -> None:
        output = UciSession().handle_line("go depth 2")
        self.assertIn("info string attempted_depth 2", output)
        self.assertTrue(output[-1].startswith("bestmove "))
        self.assertTrue(output[0].startswith("info depth 2 "))

    def test_scoreless_fallback_still_reports_depth_zero_and_nodes(self) -> None:
        output = UciSession().handle_line("go nodes 1")
        info = next(line for line in output if line.startswith("info depth"))
        self.assertIsNotNone(parse_info_line(info))


class SummaryTelemetryTests(unittest.TestCase):
    def test_lines_for_new_fields(self) -> None:
        lines = _telemetry_lines(
            {
                "terminations": {"checkmate": 5, "threefold_repetition": 2},
                "engine_moves": 100,
                "engine_moves_without_score": 7,
                "nodes_per_second_search": 8123,
            }
        )
        text = "\n".join(lines)
        self.assertIn("checkmate 5, threefold_repetition 2", text)
        self.assertIn("7 of 100", text)
        self.assertIn("8123", text)

    def test_old_results_without_the_fields_add_nothing(self) -> None:
        self.assertEqual(_telemetry_lines({}), [])


if __name__ == "__main__":
    unittest.main()
