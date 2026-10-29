"""Sequential probability ratio test (SPRT) for engine-vs-engine matches.

H0: the true Elo difference is ``elo0``. H1: it is ``elo1``. Each game is a win,
draw or loss (trinomial). For a hypothesis with expected score s the win, draw
and loss probabilities must satisfy ``p_win + p_draw / 2 = s``; the draw
probability is a nuisance parameter. The log-likelihood ratio is

    LLR = max_{p: score(p) = s1} loglik(p) - max_{p: score(p) = s0} loglik(p)

(the generalised SPRT): each hypothesis gets the draw probability that explains
the observed counts best. No smoothing is added and no observed-variance normal
approximation is used, so extreme records (16-0-0) give the true, small LLR
instead of an inflated one.

Consequence: a huge improvement is not "accepted" after a handful of games when
H1 is only a few Elo above H0. Use a larger ``elo1`` (for example 0/30) for
features expected to gain a lot.
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


def _max_loglik(wins: int, draws: int, losses: int, score: float) -> float:
    """Maximum trinomial log-likelihood over all (win, draw, loss) with this expected score.

    With draw probability t: p_win = score - t/2, p_loss = 1 - score - t/2. The
    log-likelihood is concave in t, so its derivative is bisected to zero.
    """
    t_max = 2.0 * min(score, 1.0 - score)

    def probabilities(t: float) -> tuple[float, float, float]:
        return score - t / 2.0, t, 1.0 - score - t / 2.0

    def loglik(t: float) -> float:
        total = 0.0
        for count, probability in zip((wins, draws, losses), probabilities(t)):
            if count:
                total += count * math.log(max(probability, 1e-300))
        return total

    def slope(t: float) -> float:
        p_win, p_draw, p_loss = probabilities(t)
        value = 0.0
        if wins:
            value -= wins / (2.0 * max(p_win, 1e-300))
        if draws:
            value += draws / max(p_draw, 1e-300)
        if losses:
            value -= losses / (2.0 * max(p_loss, 1e-300))
        return value

    low, high = 0.0, t_max
    for _ in range(100):
        middle = (low + high) / 2.0
        if slope(middle) > 0.0:
            low = middle
        else:
            high = middle
    return loglik((low + high) / 2.0)


def llr(wins: int, draws: int, losses: int, elo0: float, elo1: float) -> float:
    """Log-likelihood ratio of H1 against H0 for the observed W/D/L counts."""
    if wins + draws + losses == 0:
        return 0.0
    s0, s1 = expected_score(elo0), expected_score(elo1)
    return _max_loglik(wins, draws, losses, s1) - _max_loglik(wins, draws, losses, s0)


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
