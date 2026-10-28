"""Negamax search with alpha-beta pruning, quiescence and time control (Stage 4).

Features:
- Root iterative deepening up to ``depth``. With ``movetime_ms`` the search
  returns the last *fully completed* iteration, and does not start an iteration
  it is unlikely to finish. The first iteration may overrun the budget (up to
  ``FIRST_ITERATION_LIMIT`` times) so a searched move always exists; if even
  that is cut off, the best root move found so far is returned (depth 0).
- Quiescence search at the horizon (captures, en passant, queen promotions; all
  evasions when in check) so leaves are not scored in the middle of an exchange.
- Equal-scoring root moves are chosen between with a seeded RNG, so the engine
  does not shuffle and the same seed reproduces the same game.
- Mate scores encode distance to mate: ``±(MATE_SCORE - ply)``.
- No transposition table or move ordering yet (later stages).

``SearchResult.depth`` is the depth of the last completed iteration, so it is an
honest measurement: 0 means not even depth 1 finished (a legal move is still
returned).
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
MAX_DEPTH = 64
# Safety net for quiescence recursion (plies from the root).
MAX_PLY = 128
# Soft time checks every this many nodes so movetime stays responsive without
# paying a clock call on every node.
TIME_CHECK_NODES = 256
# A new iteration usually costs several times the previous one. If less than
# this multiple of the last iteration's time remains, do not start another.
NEXT_ITERATION_FACTOR = 3.0
# The first iteration may run this many times over the time budget, so a really
# searched move exists instead of an arbitrary first move. Later iterations stop
# at the normal budget.
FIRST_ITERATION_LIMIT = 2.0


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
        self._soft_deadline: float | None = None
        self._partial: tuple[Move, int] | None = None

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
        self._soft_deadline = started + movetime_ms / 1000.0 if movetime_ms is not None else None
        self._stop_deadline = (
            started + movetime_ms * FIRST_ITERATION_LIMIT / 1000.0 if movetime_ms is not None else None
        )
        self._partial = None

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
            iteration_started = time.monotonic()
            try:
                move, score = self._search_root(board, moves, iteration, rng)
            except _SearchStopped:
                if iteration == 1 and self._partial is not None:
                    # Depth 1 did not finish: use the best root move found so far
                    # (still reported as depth 0, because no iteration completed).
                    best_move, best_score = self._partial
                break
            best_move, best_score, completed_depth = move, score, iteration
            self._stop_deadline = self._soft_deadline  # Normal budget from now on.
            # Search the previous best move first next time: better pruning.
            moves.remove(move)
            moves.insert(0, move)
            if abs(score) >= MATE_SCORE - 1000:
                break  # A forced mate is found; deeper search cannot improve on it.
            if self._stop_deadline is not None:
                remaining = self._stop_deadline - time.monotonic()
                last_iteration = time.monotonic() - iteration_started
                if remaining <= 0 or remaining < last_iteration * NEXT_ITERATION_FACTOR:
                    break

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
        self._partial = None
        for move in moves:
            board.make_move(move)
            try:
                score = -self._negamax(board, depth - 1, -MATE_SCORE, -(best_score - 1), ply=1)
            finally:
                board.unmake_move()
            if score > best_score:
                best_score = score
                candidates = [move]
                self._partial = (move, score)
            elif score == best_score:
                candidates.append(move)
        chosen = candidates[0] if rng is None or len(candidates) == 1 else rng.choice(candidates)
        return chosen, best_score

    def _result(self, move: Move | None, score: int, depth: int, started: float) -> SearchResult:
        return SearchResult(
            best_move=move,
            score=score,
            depth=depth,
            nodes=self.nodes,
            time_ms=int((time.monotonic() - started) * 1000),
            mate=_mate_distance(score),
        )

    def _count_node(self) -> None:
        """Count a node and enforce the soft time limit."""
        self.nodes += 1
        if (
            self._stop_deadline is not None
            and self.nodes % TIME_CHECK_NODES == 0
            and time.monotonic() >= self._stop_deadline
        ):
            raise _SearchStopped

    def _negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        if depth <= 0:
            return self._quiesce(board, alpha, beta, ply)

        self._count_node()
        if board.is_fifty_move_draw() or board.is_threefold_repetition() or board.is_insufficient_material():
            return DRAW_SCORE

        moves = list(generate_legal_moves(board))
        if not moves:
            return self._terminal_score(board, ply)

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

    def _quiesce(self, board: Board, alpha: int, beta: int, ply: int) -> int:
        """Resolve captures until the position is quiet, then evaluate.

        Not in check: the side to move may "stand pat" (keep the static score),
        so only captures that improve on it are searched. In check: standing pat
        is illegal, so every legal evasion is searched and no evasions means mate.
        Stalemate is not detected here (stand-pat is used), a standard shortcut.
        """
        self._count_node()
        if board.is_fifty_move_draw() or board.is_threefold_repetition() or board.is_insufficient_material():
            return DRAW_SCORE
        if ply >= MAX_PLY:
            return evaluate(board)

        if board.in_check():
            moves = list(generate_legal_moves(board))
            if not moves:
                return -MATE_SCORE + ply
            best = -MATE_SCORE + ply
        else:
            best = evaluate(board)
            if best >= beta:
                return best
            if best > alpha:
                alpha = best
            moves = list(generate_legal_moves(board, captures_only=True))

        for move in moves:
            board.make_move(move)
            try:
                score = -self._quiesce(board, -beta, -alpha, ply + 1)
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
