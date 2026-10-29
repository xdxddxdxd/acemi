"""Which games count towards a match result (pure functions, no python-chess).

Games are played in colour-swapped pairs (same opening, both colours). With SPRT
only complete pairs count, and only games that had finished when the test
reached its decision: games still running at that moment are kept in the raw
PGN / move records but excluded from the result, so the recorded W/D/L, LLR and
decision all describe the same sample.
"""

from __future__ import annotations

from dataclasses import dataclass


def completed_pairs(games: list[dict]) -> list[dict]:
    """Return only games whose colour-swapped partner also completed normally."""
    pairs: dict[int, list[dict]] = {}
    for game in games:
        if game["engine_result"] != "aborted":
            pairs.setdefault(game["pair_no"], []).append(game)
    return [game for pair in pairs.values() if len(pair) == 2 for game in pair]


@dataclass(frozen=True)
class Sample:
    """The games a result is computed from, and how many finished games were left out."""

    games: list[dict]
    unpaired_excluded: int
    post_decision_excluded: int


def select_sample(
    all_games: list[dict],
    *,
    sprt_enabled: bool,
    decided_games: list[dict] | None,
) -> Sample:
    """Choose the result sample.

    ``all_games`` is every game that finished. ``decided_games`` is the snapshot of
    finished games taken when the SPRT first reached a decision (None if it never did).
    """
    finished_all = [g for g in all_games if g["engine_result"] != "aborted"]
    basis = decided_games if (sprt_enabled and decided_games is not None) else all_games
    finished_basis = [g for g in basis if g["engine_result"] != "aborted"]
    counted = completed_pairs(basis) if sprt_enabled else finished_basis
    return Sample(
        games=counted,
        unpaired_excluded=len(finished_basis) - len(counted),
        post_decision_excluded=len(finished_all) - len(finished_basis),
    )
