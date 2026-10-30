"""Opening seed completion and Stockfish balance filtering."""

import tempfile
import unittest
from pathlib import Path

import chess

from tools import openings


class FakeEvaluator:
    def __init__(self, score: int | None = 0) -> None:
        self.score = score
        self.calls = 0

    def best_move(self, board: chess.Board, depth: int) -> chess.Move:
        self.calls += 1
        return next(iter(board.legal_moves))

    def score_cp(self, board: chess.Board, depth: int) -> int | None:
        return self.score


class SeedTests(unittest.TestCase):
    def test_parse_seeds_skips_comments_and_blank_lines(self) -> None:
        text = "# header\nItalian | e2e4 e7e5 g1f3 b8c6 f1c4 f8c5\n\nSicilian | e2e4 c7c5\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seeds.txt"
            path.write_text(text, encoding="utf-8")
            seeds = openings.parse_seeds(path)
        self.assertEqual([name for name, _ in seeds], ["Italian", "Sicilian"])
        self.assertEqual(seeds[0][1], ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"])

    def test_parse_seeds_rejects_an_illegal_move(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seeds.txt"
            path.write_text("Bad | e2e4 e7e5 e2e4\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                openings.parse_seeds(path)


class CompletionTests(unittest.TestCase):
    def test_short_seed_is_extended_to_the_target_length(self) -> None:
        evaluator = FakeEvaluator()
        line = openings.complete_line(["e2e4", "c7c5"], evaluator, target_plies=10)
        self.assertEqual(len(line), 10)
        board = chess.Board()
        for move in line:
            board.push_uci(move)
        self.assertEqual(evaluator.calls, 8)

    def test_long_seed_is_truncated(self) -> None:
        seed = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "c2c3", "g8f6", "d2d3", "d7d6", "e1g1"]
        line = openings.complete_line(seed, FakeEvaluator(), target_plies=10)
        self.assertEqual(line, seed[:10])


class BuildTests(unittest.TestCase):
    SEEDS = [
        ("Italian", ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"]),
        ("Sicilian", ["e2e4", "c7c5", "g1f3", "d7d6"]),
    ]

    def test_balanced_lines_are_accepted_and_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "openings.txt"
            accepted = openings.build_openings(
                self.SEEDS, FakeEvaluator(score=20), out, target_plies=10, cp_limit=50, max_lines=64
            )
            text = out.read_text(encoding="utf-8")
        self.assertEqual(len(accepted), 2)
        self.assertIn("# Italian", text)
        self.assertIn("# Sicilian", text)
        self.assertEqual(len([line for line in text.splitlines() if line and not line.startswith("#")]), 2)

    def test_unbalanced_lines_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "openings.txt"
            accepted = openings.build_openings(
                self.SEEDS, FakeEvaluator(score=120), out, target_plies=10, cp_limit=50, max_lines=64
            )
        self.assertEqual(accepted, [])

    def test_mate_scores_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "openings.txt"
            accepted = openings.build_openings(
                self.SEEDS, FakeEvaluator(score=None), out, target_plies=10, cp_limit=50, max_lines=64
            )
        self.assertEqual(accepted, [])

    def test_duplicate_final_lines_are_kept_once(self) -> None:
        seeds = [("A", ["e2e4"]), ("B", ["e2e4"])]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "openings.txt"
            accepted = openings.build_openings(
                seeds, FakeEvaluator(score=0), out, target_plies=4, cp_limit=50, max_lines=64
            )
        self.assertEqual(len(accepted), 1)


if __name__ == "__main__":
    unittest.main()
