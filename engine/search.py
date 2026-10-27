"""Negamax search with alpha-beta pruning (Stage 3).

Scope for this stage:
- Material evaluation only (via ``engine.eval``)
- Fixed-depth or soft movetime stop
- Mate scores encode distance to mate: ``±(MATE_SCORE - ply)``
- No quiescence, transposition table, iterative deepening, or move ordering

Later stages extend this module; the public ``search`` entry point and the
``SearchResult`` shape are kept stable for the UCI layer.
"""

from __future__ import annotations

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
    depth: int
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
        self._stopped = False

    def search(
        self,
        board: Board,
        *,
        depth: int = DEFAULT_DEPTH,
        movetime_ms: int | None = None,
    ) -> SearchResult:
        """Search ``board`` and return the best move plus statistics.

        ``depth`` is the nominal fixed depth. If ``movetime_ms`` is set, search
        may stop early and return the best move found so far.
        """
        if depth < 0:
            raise ValueError("search depth cannot be negative")

        self.nodes = 0
        self._stopped = False
        self._stop_deadline = (
            time.monotonic() + movetime_ms / 1000.0 if movetime_ms is not None else None
        )
        started = time.monotonic()

        moves = list(generate_legal_moves(board))
        if not moves:
            score = self._terminal_score(board, ply=0)
            return SearchResult(
                best_move=None,
                score=score,
                depth=0,
                nodes=self.nodes,
                time_ms=int((time.monotonic() - started) * 1000),
                mate=_mate_distance(score),
            )

        # Depth 0: evaluate the static position and pick any legal move.
        if depth == 0:
            score = evaluate(board)
            return SearchResult(
                best_move=moves[0],
                score=score,
                depth=0,
                nodes=1,
                time_ms=int((time.monotonic() - started) * 1000),
                mate=None,
            )

        best_move = moves[0]
        best_score = -MATE_SCORE - 1
        alpha = -MATE_SCORE
        beta = MATE_SCORE

        for move in moves:
            board.make_move(move)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha, ply=1)
            except _SearchStopped:
                board.unmake_move()
                break
            board.unmake_move()

            if score > best_score:
                best_score = score
                best_move = move
            if score > alpha:
                alpha = score

        elapsed_ms = int((time.monotonic() - started) * 1000)
        return SearchResult(
            best_move=best_move,
            score=best_score,
            depth=depth,
            nodes=self.nodes,
            time_ms=elapsed_ms,
            mate=_mate_distance(best_score),
        )

    def _negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        if self._stop_deadline is not None and self.nodes % TIME_CHECK_NODES == 0:
            if time.monotonic() >= self._stop_deadline:
                self._stopped = True
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
            score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
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
) -> SearchResult:
    """Convenience wrapper around ``Searcher.search``."""
    return Searcher().search(board, depth=depth, movetime_ms=movetime_ms)
