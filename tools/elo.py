"""Elo estimates and confidence intervals from win/draw/loss counts.

Uses the logistic Elo model: expected score = 1 / (1 + 10 ** (-elo / 400)).
The confidence interval is the Wilson score interval on the score, with every
game counted as one trial. That is conservative when many games are draws (a draw
carries less variance than a win or loss), but it stays valid for small samples
and for scores near 0% or 100% where the plain normal interval collapses. It
ignores that games come in colour-swapped pairs, so it is not "always
conservative" about the pairing either way. The point estimate is undefined at 0%
or 100% (infinite Elo).
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass


def expected_score(elo_diff: float) -> float:
    """Expected score (0..1) for a player who is ``elo_diff`` Elo stronger."""
    return 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))


def score_to_elo(score: float) -> float | None:
    """Elo difference implied by a score, or None at 0% / 100% (infinite)."""
    if score <= 0.0 or score >= 1.0:
        return None
    return -400.0 * math.log10(1.0 / score - 1.0)


@dataclass(frozen=True)
class EloEstimate:
    games: int
    score: float | None
    elo: float | None
    low: float | None
    high: float | None


def wilson_interval(score: float, games: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a score observed over ``games`` games."""
    z2 = z * z
    centre = (score + z2 / (2.0 * games)) / (1.0 + z2 / games)
    half = z * math.sqrt(score * (1.0 - score) / games + z2 / (4.0 * games * games)) / (1.0 + z2 / games)
    return max(0.0, centre - half), min(1.0, centre + half)


def estimate(wins: int, draws: int, losses: int, z: float = 1.96) -> EloEstimate:
    """Elo difference and a ~95% Wilson interval (z=1.96) from W/D/L counts.

    Bounds that fall at or beyond a 0% / 100% score are returned as None.
    """
    games = wins + draws + losses
    if games == 0:
        return EloEstimate(0, None, None, None, None)
    score = (wins + 0.5 * draws) / games
    low, high = wilson_interval(score, games, z)
    return EloEstimate(
        games=games,
        score=score,
        elo=score_to_elo(score),
        low=score_to_elo(low) if low > 1e-12 else None,
        high=score_to_elo(high) if high < 1.0 - 1e-12 else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Elo difference from W/D/L counts.")
    parser.add_argument("wins", type=int)
    parser.add_argument("draws", type=int)
    parser.add_argument("losses", type=int)
    args = parser.parse_args()
    result = estimate(args.wins, args.draws, args.losses)
    print(result)


if __name__ == "__main__":
    main()
