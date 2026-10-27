"""Elo and SPRT helper tests (pure arithmetic, no engines involved)."""

import math
import unittest

from tools import elo, sprt


class EloTests(unittest.TestCase):
    def test_expected_score_at_equal_strength(self) -> None:
        self.assertAlmostEqual(elo.expected_score(0.0), 0.5)

    def test_expected_score_for_400_elo_edge(self) -> None:
        self.assertAlmostEqual(elo.expected_score(400.0), 1.0 / 1.1, places=9)

    def test_score_to_elo_round_trip(self) -> None:
        self.assertAlmostEqual(elo.score_to_elo(elo.expected_score(123.0)), 123.0, places=6)

    def test_score_to_elo_is_undefined_at_extremes(self) -> None:
        self.assertIsNone(elo.score_to_elo(0.0))
        self.assertIsNone(elo.score_to_elo(1.0))

    def test_even_match_is_zero_with_interval_around_zero(self) -> None:
        result = elo.estimate(30, 40, 30)
        self.assertEqual(result.games, 100)
        self.assertAlmostEqual(result.elo, 0.0, places=9)
        self.assertLess(result.low, 0.0)
        self.assertGreater(result.high, 0.0)

    def test_no_games_has_no_estimate(self) -> None:
        result = elo.estimate(0, 0, 0)
        self.assertEqual(result.games, 0)
        self.assertIsNone(result.elo)

    def test_perfect_score_has_no_finite_estimate(self) -> None:
        self.assertIsNone(elo.estimate(10, 0, 0).elo)


class SprtTests(unittest.TestCase):
    def test_log_bounds_for_five_percent_errors(self) -> None:
        lower, upper = sprt.log_bounds(0.05, 0.05)
        self.assertAlmostEqual(upper, math.log(19.0), places=9)
        self.assertAlmostEqual(lower, -math.log(19.0), places=9)

    def test_no_games_gives_zero_llr(self) -> None:
        self.assertEqual(sprt.llr(0, 0, 0, 0.0, 10.0), 0.0)

    def test_winning_record_gives_positive_llr(self) -> None:
        self.assertGreater(sprt.llr(60, 0, 40, 0.0, 10.0), 0.0)

    def test_losing_record_gives_negative_llr(self) -> None:
        self.assertLess(sprt.llr(40, 0, 60, 0.0, 10.0), 0.0)

    def test_decisions(self) -> None:
        self.assertEqual(sprt.decide(3.0, 0.05, 0.05), "accept_h1")
        self.assertEqual(sprt.decide(-3.0, 0.05, 0.05), "accept_h0")
        self.assertEqual(sprt.decide(0.0, 0.05, 0.05), "continue")


if __name__ == "__main__":
    unittest.main()
