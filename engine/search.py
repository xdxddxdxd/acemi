"""Negamax search with alpha-beta pruning (Stage 3).

Scope for this stage:
- Material evaluation only (via ``engine.eval``)
- Root iterative deepening up to ``depth``; with ``movetime_ms`` the search
  returns the last *fully completed* iteration, never a half-searched one
- Equal-scoring root moves are chosen between with a seeded RNG (otherwise the
  first generated move would always win ties and the engine would shuffle)
- Mate scores encode distance to mate: ``±(MATE_SCORE - ply)``
- No quiescence, transposition table, or move ordering (later stages)

``SearchResult.depth`` is the depth of the last completed iteration, so it is
an honest measurement: 0 means not even depth 1 finished (a legal move is still
returned).

The public ``search`` entry point and the ``SearchResult`` shape are kept stable
for the UCI layer.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from engine.board import Board, Move
from engine.eval.base import evaluate
from engine.movegen import generate_legal_moves

MATE_SCORE = 100_000
DRAW_SCORE = 0
DEFAULT_DEPTH = 3
# Soft time checks every this many nodes so movetime stays responsive without
# paying a clock call on every node.
TIME_CHECK_NODES = 256


@dataclass(slots=True)
class SearchResult:
    best_move: Move | None
    score: int
    depth: int  # last fully completed iteration (0 = none, or no search was needed)
    nodes: int
    time_ms: int
    mate: int | None  # positive = we mate in N, negative = we are mated in N


class _SearchStopped(Exception):
    """Raised internally when a soft time limit is hit."""


class Searcher:
    """Stateful searcher so node counts and stop flags stay on one object."""

    def __init__(self) -> None:
        self.nodes = 0
        self._stop_deadline: float | None = None

    def search(
        self,
        board: Board,
        *,
        depth: int = DEFAULT_DEPTH,
        movetime_ms: int | None = None,
        rng: random.Random | None = None,
    ) -> SearchResult:
        """Search ``board`` and return the best move plus statistics.

        ``depth`` is the maximum iteration depth. If ``movetime_ms`` is set, the
        search stops at the deadline and returns the last completed iteration.
        ``rng`` picks between equally good root moves; without it the first
        such move is used (deterministic, handy for tests).
        """
        if depth < 0:
            raise ValueError("search depth cannot be negative")

        self.nodes = 0
        started = time.monotonic()
        self._stop_deadline = started + movetime_ms / 1000.0 if movetime_ms is not None else None

        moves = list(generate_legal_moves(board))
        if not moves:
            score = self._terminal_score(board, ply=0)
            return self._result(None, score, 0, started)

        if depth == 0:
            self.nodes = 1
            return self._result(moves[0], evaluate(board), 0, started)

        # Fallback if not even depth 1 completes: a legal move, no score claim.
        best_move: Move = moves[0]
        best_score = 0
        completed_depth = 0

        for iteration in range(1, depth + 1):
            if iteration > 1 and self._deadline_passed():
                break
            try:
                move, score = self._search_root(board, moves, iteration, rng)
            except _SearchStopped:
                break
            best_move, best_score, completed_depth = move, score, iteration
            # Search the previous best move first next time: better pruning.
            moves.remove(move)
            moves.insert(0, move)
            if abs(score) >= MATE_SCORE - 1000:
                break  # A forced mate is found; deeper search cannot improve on it.

        return self._result(best_move, best_score, completed_depth, started)

    def _search_root(
        self, board: Board, moves: list[Move], depth: int, rng: random.Random | None
    ) -> tuple[Move, int]:
        """Search every root move to ``depth``; return one of the best moves and its score.

        The alpha window is kept one point below the best score so moves that
        tie the best score come back with their exact value and can be told
        apart from worse moves (fail-soft bounds are always below the window).
        """
        best_score = -MATE_SCORE - 1
        candidates: list[Move] = []
        for move in moves:
            board.make_move(move)
            try:
                score = -self._negamax(board, depth - 1, -MATE_SCORE, -(best_score - 1), ply=1)
            finally:
                board.unmake_move()
            if score > best_score:
                best_score = score
                candidates = [move]
            elif score == best_score:
                candidates.append(move)
        chosen = candidates[0] if rng is None or len(candidates) == 1 else rng.choice(candidates)
        return chosen, best_score

    def _deadline_passed(self) -> bool:
        return self._stop_deadline is not None and time.monotonic() >= self._stop_deadline

    def _result(self, move: Move | None, score: int, depth: int, started: float) -> SearchResult:
        return SearchResult(
            best_move=move,
            score=score,
            depth=depth,
            nodes=self.nodes,
            time_ms=int((time.monotonic() - started) * 1000),
            mate=_mate_distance(score),
        )

    def _negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        if self._stop_deadline is not None and self.nodes % TIME_CHECK_NODES == 0:
            if time.monotonic() >= self._stop_deadline:
                raise _SearchStopped

        if board.is_fifty_move_draw() or board.is_threefold_repetition() or board.is_insufficient_material():
            return DRAW_SCORE

        moves = list(generate_legal_moves(board))
        if not moves:
            return self._terminal_score(board, ply)

        if depth == 0:
            return evaluate(board)

        best = -MATE_SCORE
        for move in moves:
            board.make_move(move)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.unmake_move()
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        return best

    @staticmethod
    def _terminal_score(board: Board, ply: int) -> int:
        """Mate or stalemate score from the side that has just run out of moves."""
        if board.in_check():
            return -MATE_SCORE + ply
        return DRAW_SCORE


def _mate_distance(score: int) -> int | None:
    """Convert an internal mate score to UCI mate distance, or None if not mate."""
    if score >= MATE_SCORE - 1000:
        return (MATE_SCORE - score + 1) // 2
    if score <= -MATE_SCORE + 1000:
        return -((MATE_SCORE + score + 1) // 2)
    return None


def search(
    board: Board,
    *,
    depth: int = DEFAULT_DEPTH,
    movetime_ms: int | None = None,
    rng: random.Random | None = None,
) -> SearchResult:
    """Convenience wrapper around ``Searcher.search``."""
    return Searcher().search(board, depth=depth, movetime_ms=movetime_ms, rng=rng)
