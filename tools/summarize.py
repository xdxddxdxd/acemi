"""Factual SUMMARY.md generator. Facts only: no causes, no recommendations."""

from __future__ import annotations

from collections import defaultdict

TOP_LOST_OPENINGS = 10
PHASES = ("opening", "middlegame", "endgame")


def _number(value: float | int | None, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "not measured"
    if isinstance(value, int):
        return f"{value}{suffix}"
    return f"{value:.{digits}f}{suffix}"


def _elo_line(results: dict) -> str:
    elo = results.get("elo_diff")
    if elo is None:
        return "- Elo difference: not defined (no games, or a 0% / 100% score)"
    interval = results.get("elo_confidence_interval")
    if not interval:
        return f"- Elo difference: {elo:+.1f}"
    low = "unbounded" if interval[0] is None else f"{interval[0]:+.1f}"
    high = "unbounded" if interval[1] is None else f"{interval[1]:+.1f}"
    return f"- Elo difference: {elo:+.1f} (95% interval {low} to {high}; normal approximation)"


def _sprt_line(sprt: dict) -> str:
    if not sprt.get("enabled"):
        return "- SPRT: not run"
    llr = sprt.get("llr")
    llr_text = "n/a" if llr is None else f"{llr:.2f}"
    return (
        f"- SPRT: {sprt['decision']} (LLR {llr_text}, bounds "
        f"{sprt['lower_bound']:.2f} / {sprt['upper_bound']:.2f}; elo0={sprt['elo0']}, "
        f"elo1={sprt['elo1']}, alpha={sprt['alpha']}, beta={sprt['beta']}, "
        f"max games={sprt['max_games']})"
    )


def _opening_lines(games: list[dict]) -> list[str]:
    tally: dict[tuple[int, str], dict[str, int]] = defaultdict(
        lambda: {"win": 0, "draw": 0, "loss": 0}
    )
    for game in games:
        if game["engine_result"] in ("win", "draw", "loss"):
            tally[(game["opening_id"], game["opening"])][game["engine_result"]] += 1
    lost = [(key, counts) for key, counts in tally.items() if counts["loss"] > 0]
    if not lost:
        return ["- Opening results (Acemi W/D/L): no losses in any opening"]
    lost.sort(key=lambda item: (-item[1]["loss"], -sum(item[1].values()), item[0][0]))
    lines = [f"- Openings with the most losses (up to {TOP_LOST_OPENINGS}, Acemi W/D/L):"]
    for (_, name), counts in lost[:TOP_LOST_OPENINGS]:
        lines.append(f"  - {name}: {counts['win']}/{counts['draw']}/{counts['loss']}")
    return lines


def _phase_line(games: list[dict]) -> str:
    counts = {phase: 0 for phase in PHASES}
    for game in games:
        if game["engine_result"] == "loss":
            counts[game["end_phase"]] += 1
    body = "; ".join(f"{phase} {counts[phase]}" for phase in PHASES)
    return (
        f"- Losses by game phase at game end ({body}). "
        "Phase: opening = game ended within 20 plies; endgame = non-pawn material "
        "of both sides totals 26 or less (N/B=3, R=5, Q=9); otherwise middlegame"
    )


def _telemetry_lines(results: dict) -> list[str]:
    lines: list[str] = []
    terminations = results.get("terminations")
    if terminations:
        body = ", ".join(f"{name} {count}" for name, count in terminations.items())
        lines.append(f"- Game endings: {body}")
    without_score = results.get("engine_moves_without_score")
    total = results.get("engine_moves")
    if without_score is not None and total:
        lines.append(
            f"- Engine moves without a search score: {without_score} of {total} "
            "(average depth and nodes/second above include only moves that reported them)"
        )
    search_nps = results.get("nodes_per_second_search")
    if search_nps is not None:
        lines.append(
            f"- Nodes/second by the engine's own search time: {_number(search_nps, 0)} "
            "(the figure above divides by wall clock including pipe latency)"
        )
    return lines


def build_summary(meta: dict, results: dict, games: list[dict]) -> str:
    """Return SUMMARY.md text for one run.

    ``games`` rows need: opening_id, opening, engine_result (win/draw/loss/aborted),
    plies, end_phase.
    """
    opponent = meta["opponent"]
    opponent_text = f"{opponent['name']} {opponent['version']}".strip()
    if opponent.get("uci_elo") is not None:
        opponent_text += f" (UCI_Elo {opponent['uci_elo']})"
    engine_text = f"{meta.get('engine_name', 'Acemi')} {meta['engine_version']}"

    lines = [
        f"# {meta['run_name']}",
        "",
        f"- Engine: {engine_text}; opponent: {opponent_text}",
        f"- Opening set: {meta['opening_set']}; move time: {meta['engine_settings']['move_time_ms']} ms",
        f"- Games: {results['games']} (W/D/L: {results['wins']}/{results['draws']}/{results['losses']}), "
        f"score: {_number(results['score_pct'], 1, '%')}",
        _elo_line(results),
        _sprt_line(results["sprt"]),
        f"- Completed games: {results['games']}; aborted games: {results['aborted_games']}; "
        f"average plies: {_number(results['average_plies'])}",
        f"- Timeouts: {results['timeouts']}; illegal moves: {results['illegal_moves']}; "
        f"engine crashes: {results['engine_crashes']}; "
        f"board disagreements (Acemi board vs python-chess): {results['board_disagreements']}",
        f"- Average depth: {_number(results['average_depth'])}; "
        f"nodes/second: {_number(results['nodes_per_second'], 0)}",
        *_opening_lines(games),
        _phase_line(games),
        *_telemetry_lines(results),
    ]
    excluded = results.get("unpaired_games_excluded", 0)
    if excluded:
        lines.append(
            f"- Unpaired games excluded from result and SPRT: {excluded} "
            "(retained in raw PGN/move artifacts)"
        )
    post_decision = results.get("post_decision_games_excluded", 0)
    if post_decision:
        lines.append(
            f"- Games finished after the SPRT decision, excluded from result and SPRT: {post_decision} "
            "(retained in raw PGN/move artifacts)"
        )
    if opponent.get("uci_elo") is not None:
        lines.append(
            "- Note: the opponent's UCI_Elo is a rough scale and is not directly "
            "comparable with Lichess or CCRL ratings"
        )
    return "\n".join(lines) + "\n"
