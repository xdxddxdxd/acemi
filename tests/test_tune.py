"""Texel-style tuning: position features must reproduce the classical evaluation."""

import math
import unittest

from engine.board import Board
from engine.eval.base import evaluate
from engine.eval.classic import MATERIAL
from tools import tune

SAMPLE_FENS = (
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
    "r2q1rk1/ppp2ppp/2np1n2/2b1p3/2B1P1b1/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 8",
    "4k3/8/8/8/8/8/8/4K3 b - - 0 1",
)


class FeatureTests(unittest.TestCase):
    def test_start_position_is_symmetric(self) -> None:
        material, features = tune.position_terms(SAMPLE_FENS[0])
        self.assertEqual(material, 0)
        self.assertFalse(features.any())

    def test_matches_the_classical_evaluation(self) -> None:
        for fen in SAMPLE_FENS:
            with self.subTest(fen=fen):
                material, features = tune.position_terms(fen)
                score = material + float(features @ tune.initial_parameters())
                expected = evaluate(Board(fen))
                self.assertLessEqual(abs(expected - int(score)), 1)

    def test_parameter_count(self) -> None:
        self.assertEqual(len(tune.initial_parameters()), tune.PST_PARAMETERS)
        self.assertEqual(tune.PST_PARAMETERS, 6 * 64 * 2)

class GradientTests(unittest.TestCase):
    def test_gradient_matches_finite_differences(self) -> None:
        import numpy as np

        rng = np.random.default_rng(3)
        features = rng.normal(size=(12, tune.PST_PARAMETERS)).astype(np.float64)
        material = rng.integers(-500, 500, size=12).astype(np.float64)
        target = rng.integers(0, 3, size=12) / 2.0  # 0, 0.5, 1
        weights = rng.uniform(0.5, 3.0, size=12)
        params = rng.normal(scale=10.0, size=tune.PST_PARAMETERS)
        initial = tune.initial_parameters()
        loss, gradient = tune.loss_and_gradient(features, material, target, weights, params, 1e-4, initial)
        epsilon = 1e-5
        for index in (0, 57, tune.PST_PARAMETERS - 1):
            shifted = params.copy()
            shifted[index] += epsilon
            loss_plus, _ = tune.loss_and_gradient(features, material, target, weights, shifted, 1e-4, initial)
            shifted[index] -= 2 * epsilon
            loss_minus, _ = tune.loss_and_gradient(features, material, target, weights, shifted, 1e-4, initial)
            numeric = (loss_plus - loss_minus) / (2 * epsilon)
            self.assertAlmostEqual(gradient[index], numeric, places=5)
        self.assertTrue(math.isfinite(loss))


if __name__ == "__main__":
    unittest.main()
