"""Elo estimates and confidence intervals from win/draw/loss counts.

Uses the logistic Elo model: expected score = 1 / (1 + 10 ** (-elo / 400)).
The confidence interval is a normal approximation on the per-game score, so it
is rough for small game counts and undefined at 0% or 100% scores.
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


def estimate(wins: int, draws: int, losses: int, z: float = 1.96) -> EloEstimate:
    """Elo difference and a ~95% interval (z=1.96) from W/D/L counts.

    Bounds that fall at or beyond a 0% / 100% score are returned as None.
    """
    games = wins + draws + losses
    if games == 0:
        return EloEstimate(0, None, None, None, None)
    score = (wins + 0.5 * draws) / games
    variance = (
        wins * (1.0 - score) ** 2 + draws * (0.5 - score) ** 2 + losses * score**2
    ) / games
    margin = z * math.sqrt(variance / games)
    return EloEstimate(
        games=games,
        score=score,
        elo=score_to_elo(score),
        low=score_to_elo(score - margin),
        high=score_to_elo(score + margin),
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
