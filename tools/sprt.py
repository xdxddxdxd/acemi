"""Sequential probability ratio test (SPRT) for engine-vs-engine matches.

H0: the true Elo difference is ``elo0``. H1: it is ``elo1``. The log-likelihood
ratio uses the normal (GSPRT) approximation on the per-game score:

    LLR = N * (s1 - s0) * (2 * s - s0 - s1) / (2 * variance)

where s is the observed score and s0 / s1 are the expected scores under H0 / H1.
Half a game is added to each of W, D and L so the variance is never zero.

Openings are played in colour-swapped pairs, which makes the trinomial variance
slightly pessimistic; the test stays valid, just a little conservative.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

from tools.elo import expected_score


def log_bounds(alpha: float, beta: float) -> tuple[float, float]:
    """Return (lower, upper) LLR bounds for the given error rates."""
    lower = math.log(beta / (1.0 - alpha))
    upper = math.log((1.0 - beta) / alpha)
    return lower, upper


def llr(wins: int, draws: int, losses: int, elo0: float, elo1: float) -> float:
    """Log-likelihood ratio of H1 against H0 for the observed W/D/L counts."""
    if wins + draws + losses == 0:
        return 0.0
    w, d, l = wins + 0.5, draws + 0.5, losses + 0.5
    games = w + d + l
    score = (w + 0.5 * d) / games
    variance = (w * (1.0 - score) ** 2 + d * (0.5 - score) ** 2 + l * score**2) / games
    s0, s1 = expected_score(elo0), expected_score(elo1)
    return games * (s1 - s0) * (2.0 * score - s0 - s1) / (2.0 * variance)


def decide(value: float, alpha: float, beta: float) -> str:
    """Map an LLR value to ``accept_h1``, ``accept_h0`` or ``continue``."""
    lower, upper = log_bounds(alpha, beta)
    if value >= upper:
        return "accept_h1"
    if value <= lower:
        return "accept_h0"
    return "continue"


@dataclass(frozen=True)
class SprtStatus:
    llr: float
    lower_bound: float
    upper_bound: float
    decision: str


def status(
    wins: int,
    draws: int,
    losses: int,
    elo0: float,
    elo1: float,
    alpha: float = 0.05,
    beta: float = 0.05,
) -> SprtStatus:
    value = llr(wins, draws, losses, elo0, elo1)
    lower, upper = log_bounds(alpha, beta)
    return SprtStatus(value, lower, upper, decide(value, alpha, beta))


def main() -> None:
    parser = argparse.ArgumentParser(description="SPRT status from W/D/L counts.")
    parser.add_argument("wins", type=int)
    parser.add_argument("draws", type=int)
    parser.add_argument("losses", type=int)
    parser.add_argument("--elo0", type=float, default=0.0)
    parser.add_argument("--elo1", type=float, default=10.0)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--beta", type=float, default=0.05)
    args = parser.parse_args()
    print(status(args.wins, args.draws, args.losses, args.elo0, args.elo1, args.alpha, args.beta))


if __name__ == "__main__":
    main()
