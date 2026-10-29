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

    def test_wilson_interval_reference_values(self) -> None:
        low, high = elo.wilson_interval(0.5, 100)
        self.assertAlmostEqual(low, 0.4038, places=3)
        self.assertAlmostEqual(high, 0.5962, places=3)
        low, high = elo.wilson_interval(1.0, 16)
        self.assertAlmostEqual(low, 0.8061, places=3)
        self.assertAlmostEqual(high, 1.0, places=9)

    def test_perfect_record_has_a_finite_lower_bound_only(self) -> None:
        result = elo.estimate(16, 0, 0)
        self.assertIsNone(result.elo)
        self.assertIsNone(result.high)
        self.assertGreater(result.low, 240.0)

    def test_small_sample_interval_is_wider_than_the_normal_approximation(self) -> None:
        # 4 wins, 2 draws, 14 losses: the normal interval was [-441, -51].
        result = elo.estimate(4, 2, 14)
        self.assertLess(result.low, -280.0)
        self.assertGreater(result.high, -60.0)
        self.assertLess(result.high, -10.0)


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

    @staticmethod
    def _brute_force_llr(wins: int, draws: int, losses: int, elo0: float, elo1: float) -> float:
        """Independent reference: grid search over the draw probability."""

        def best(score: float) -> float:
            t_max = 2.0 * min(score, 1.0 - score)
            top = -math.inf
            steps = 20000
            for i in range(steps + 1):
                t = t_max * i / steps
                probabilities = (score - t / 2.0, t, 1.0 - score - t / 2.0)
                total = 0.0
                for count, p in zip((wins, draws, losses), probabilities):
                    if count:
                        total += count * math.log(max(p, 1e-300))
                top = max(top, total)
            return top

        return best(elo.expected_score(elo1)) - best(elo.expected_score(elo0))

    def test_llr_matches_brute_force_maximum_likelihood(self) -> None:
        for counts in [(42, 9, 3), (26, 22, 88), (102, 119, 79), (46, 38, 16), (3, 0, 7), (0, 10, 0)]:
            with self.subTest(counts=counts):
                self.assertAlmostEqual(
                    sprt.llr(*counts, 0.0, 10.0), self._brute_force_llr(*counts, 0.0, 10.0), places=3
                )

    def test_reference_values(self) -> None:
        # Values that the old observed-variance formula inflated (3.34 / 3.28 / 3.26).
        self.assertAlmostEqual(sprt.llr(16, 0, 0, 0.0, 10.0), 0.4539, places=3)
        self.assertAlmostEqual(sprt.llr(42, 9, 3, 0.0, 10.0), 1.3235, places=3)
        self.assertAlmostEqual(sprt.llr(41, 6, 3, 0.0, 10.0), 1.2214, places=3)

    def test_without_draws_it_is_the_bernoulli_ratio(self) -> None:
        s0, s1 = elo.expected_score(0.0), elo.expected_score(10.0)
        expected = 16 * math.log(s1 / s0)
        self.assertAlmostEqual(sprt.llr(16, 0, 0, 0.0, 10.0), expected, places=9)
        expected = 7 * math.log(1 - s1) - 7 * math.log(1 - s0) + 3 * math.log(s1 / s0)
        self.assertAlmostEqual(sprt.llr(3, 0, 7, 0.0, 10.0), expected, places=9)

    def test_swapping_sides_and_hypotheses_keeps_the_llr(self) -> None:
        self.assertAlmostEqual(sprt.llr(30, 12, 8, 0.0, 10.0), sprt.llr(8, 12, 30, 0.0, -10.0), places=9)

    def test_a_perfect_short_record_is_not_accepted(self) -> None:
        self.assertEqual(sprt.status(16, 0, 0, 0.0, 10.0).decision, "continue")
        self.assertEqual(sprt.status(42, 9, 3, 0.0, 10.0).decision, "continue")

    def test_larger_elo1_accepts_a_big_gain(self) -> None:
        self.assertEqual(sprt.status(42, 9, 3, 0.0, 30.0).decision, "accept_h1")

    def test_all_draws_favour_h0(self) -> None:
        self.assertLess(sprt.llr(0, 40, 0, 0.0, 10.0), 0.0)

    def test_decisions(self) -> None:
        self.assertEqual(sprt.decide(3.0, 0.05, 0.05), "accept_h1")
        self.assertEqual(sprt.decide(-3.0, 0.05, 0.05), "accept_h0")
        self.assertEqual(sprt.decide(0.0, 0.05, 0.05), "continue")


if __name__ == "__main__":
    unittest.main()
