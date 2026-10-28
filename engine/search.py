"""Negamax search with alpha-beta pruning, quiescence, move ordering and a
transposition table (Stage 5).

Features:
- Root iterative deepening up to ``depth``. With ``movetime_ms`` the search
  returns the last *fully completed* iteration, and does not start an iteration
  it is unlikely to finish. If the first iteration is interrupted, the best
  root move found so far is returned with depth 0 and no fabricated eval.
- Move ordering: transposition-table move first, then captures by MVV-LVA (most
  valuable victim, least valuable attacker), then promotions, then quiet moves
  by piece-square gain. Good ordering is what makes alpha-beta cut early, and it
  also makes an interrupted first iteration return a sensible move.
- Transposition table (Python dict keyed by the Zobrist hash) with exact, lower
  and upper bounds, depth-preferred replacement and mate-distance correction.
  The table survives between searches of one game (a persistent ``Searcher``);
  its size follows the UCI ``Hash`` option.
- Quiescence search at the horizon (captures, en passant, queen promotions; all
  evasions when in check) so leaves are not scored in the middle of an exchange.
- Equal-scoring root moves are chosen between with a seeded RNG, so the engine
  does not shuffle and the same seed reproduces the same game.
- Mate scores encode distance to mate: ``±(MATE_SCORE - ply)``.
- No null move, LMR, killer or history heuristics yet (Stage 6).

``SearchResult.depth`` is the depth of the last completed iteration, so it is an
honest measurement: 0 means not even depth 1 finished (a legal move is still
returned).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from threading import Event

from engine.board import PAWN, Board, Move
from engine.eval.base import evaluate
from engine.eval.classic import pst_delta
from engine.movegen import generate_legal_moves

MATE_SCORE = 100_000
DRAW_SCORE = 0
DEFAULT_DEPTH = 3
MAX_DEPTH = 64
# Safety net for quiescence recursion (plies from the root).
MAX_PLY = 128
# Time checks are frequent enough to keep movetime and external stop responsive
# without paying a clock call on every node.
TIME_CHECK_NODES = 64
# A new iteration usually costs several times the previous one. If less than
# this multiple of the last iteration's time remains, do not start another.
NEXT_ITERATION_FACTOR = 3.0

# Transposition table.
DEFAULT_HASH_MB = 16
# Rough capacity per megabyte of the UCI Hash option (Python tuples and a dict
# are far bigger than a C table entry, so this is an approximation).
TT_ENTRIES_PER_MB = 5000
TT_EXACT = 0
TT_LOWER = 1  # The true score is at least the stored score (a beta cutoff).
TT_UPPER = 2  # The true score is at most the stored score (all moves failed low).
MATE_BOUND = MATE_SCORE - 1000


@dataclass(slots=True)
class SearchResult:
    best_move: Move | None
    score: int | None
    depth: int  # last fully completed iteration (0 = none, or no search was needed)
    nodes: int
    time_ms: int
    mate: int | None  # positive = we mate in N, negative = we are mated in N


class _SearchStopped(Exception):
    """Raised internally when a soft time limit is hit."""


# -- move ordering ----------------------------------------------------------


def _move_score(board: Board, move: Move) -> int:
    """Ordering score: captures (MVV-LVA) > promotions > quiet moves by PST gain."""
    squares = board.squares
    moving_piece = squares[move.from_square]
    attacker = abs(moving_piece)
    victim_piece = squares[move.to_square]
    if victim_piece:
        victim = abs(victim_piece)
    elif (
        attacker == PAWN
        and move.to_square == board.en_passant_square
        and (move.from_square & 7) != (move.to_square & 7)
    ):
        victim = PAWN
    else:
        victim = 0

    if victim:
        score = 1000 + 10 * victim - attacker
    else:
        # Quiet move: small piece-square gain, always below every capture.
        score = pst_delta(moving_piece, move.from_square, move.to_square) // 10
    if move.promotion is not None:
        score += 600 + move.promotion
    return score


def order_moves(board: Board, moves: list[Move], first: Move | None = None) -> None:
    """Sort ``moves`` in place, best first; ``first`` (e.g. the TT move) goes to the front.

    The sort is stable, so equal scores keep the generator's order and the
    result is deterministic.
    """
    moves.sort(key=lambda move: _move_score(board, move), reverse=True)
    if first is not None and moves and moves[0] != first:
        try:
            index = moves.index(first)
        except ValueError:
            return  # Stale or colliding table entry: ignore it.
        moves.insert(0, moves.pop(index))


# -- transposition table helpers ---------------------------------------------


def to_tt_score(score: int, ply: int) -> int:
    """Make a mate score independent of the root distance before storing it."""
    if score >= MATE_BOUND:
        return score + ply
    if score <= -MATE_BOUND:
        return score - ply
    return score


def from_tt_score(score: int, ply: int) -> int:
    """Inverse of ``to_tt_score`` for the node being probed."""
    if score >= MATE_BOUND:
        return score - ply
    if score <= -MATE_BOUND:
        return score + ply
    return score


class Searcher:
    """Stateful searcher: node counts, stop flags and the transposition table."""

    def __init__(self, hash_mb: int = DEFAULT_HASH_MB) -> None:
        self.nodes = 0
        self._deadline: float | None = None
        self._nodes_limit: int | None = None
        self._stop_event: Event | None = None
        self._partial: tuple[Move, int] | None = None
        self._tt: dict[int, tuple[int, int, int, Move | None]] = {}
        self._tt_max = 0
        self.resize_tt(hash_mb)

    # -- table management ---------------------------------------------------

    def resize_tt(self, hash_mb: int) -> None:
        """Set the table capacity from a size in megabytes (0 disables it) and clear it."""
        self._tt_max = max(0, hash_mb) * TT_ENTRIES_PER_MB
        self._tt.clear()

    def clear_tt(self) -> None:
        self._tt.clear()

    @property
    def tt_size(self) -> int:
        return len(self._tt)

    @property
    def tt_capacity(self) -> int:
        return self._tt_max

    def _store(self, key: int, depth: int, flag: int, score: int, move: Move | None) -> None:
        if self._tt_max <= 0:
            return
        old = self._tt.get(key)
        if old is not None:
            if old[0] > depth:
                return  # Keep the deeper result for this position.
        elif len(self._tt) >= self._tt_max:
            self._tt.clear()  # Full: start over (simple and cheap).
        self._tt[key] = (depth, flag, score, move)

    # -- search -------------------------------------------------------------

    def search(
        self,
        board: Board,
        *,
        depth: int = DEFAULT_DEPTH,
        movetime_ms: int | None = None,
        nodes_limit: int | None = None,
        stop_event: Event | None = None,
        rng: random.Random | None = None,
    ) -> SearchResult:
        """Search ``board`` and return the best move plus statistics.

        ``depth`` is the maximum iteration depth. Time, node and external stop
        limits interrupt the current iteration and return the last completed one.
        ``rng`` picks between equally good root moves; without it the first
        such move is used (deterministic, handy for tests).
        """
        if depth < 0:
            raise ValueError("search depth cannot be negative")
        if nodes_limit is not None and nodes_limit < 0:
            raise ValueError("nodes limit cannot be negative")

        self.nodes = 0
        started = time.monotonic()
        self._deadline = started + movetime_ms / 1000.0 if movetime_ms is not None else None
        self._nodes_limit = nodes_limit
        self._stop_event = stop_event
        self._partial = None

        moves = list(generate_legal_moves(board))
        if not moves:
            score = self._terminal_score(board, ply=0)
            return self._result(None, score, 0, started)

        root_entry = self._tt.get(board.zobrist_hash)
        order_moves(board, moves, None if root_entry is None else root_entry[3])

        if depth == 0:
            self.nodes = 1
            return self._result(moves[0], evaluate(board), 0, started)

        # Fallback if not even depth 1 completes: the best-ordered legal move,
        # no score claim.
        best_move: Move = moves[0]
        best_score: int | None = None
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
            self._store(board.zobrist_hash, iteration, TT_EXACT, to_tt_score(score, 0), move)
            # Search the previous best move first next time: better pruning.
            moves.remove(move)
            moves.insert(0, move)
            if abs(score) >= MATE_SCORE - 1000:
                break  # A forced mate is found; deeper search cannot improve on it.
            if self._deadline is not None:
                remaining = self._deadline - time.monotonic()
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
            self._check_stopped()
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

    def _result(self, move: Move | None, score: int | None, depth: int, started: float) -> SearchResult:
        return SearchResult(
            best_move=move,
            score=score,
            depth=depth,
            nodes=self.nodes,
            time_ms=int((time.monotonic() - started) * 1000),
            mate=None if score is None else _mate_distance(score),
        )

    def _check_stopped(self) -> None:
        if self._stop_event is not None and self._stop_event.is_set():
            raise _SearchStopped
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise _SearchStopped

    def _count_node(self) -> None:
        """Count a node and enforce node, time and external stop limits."""
        self.nodes += 1
        if self._nodes_limit is not None and self.nodes >= self._nodes_limit:
            raise _SearchStopped
        if self.nodes % TIME_CHECK_NODES == 0:
            self._check_stopped()

    def _negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        if depth <= 0:
            return self._quiesce(board, alpha, beta, ply)

        self._count_node()
        if board.is_fifty_move_draw() or board.is_threefold_repetition() or board.is_insufficient_material():
            return DRAW_SCORE

        key = board.zobrist_hash
        tt_move: Move | None = None
        entry = self._tt.get(key)
        if entry is not None:
            entry_depth, flag, entry_score, tt_move = entry
            if entry_depth >= depth:
                score = from_tt_score(entry_score, ply)
                if (
                    flag == TT_EXACT
                    or (flag == TT_LOWER and score >= beta)
                    or (flag == TT_UPPER and score <= alpha)
                ):
                    return score

        moves = list(generate_legal_moves(board))
        self._check_stopped()
        if not moves:
            return self._terminal_score(board, ply)
        order_moves(board, moves, tt_move)

        original_alpha = alpha
        best = -MATE_SCORE
        best_move: Move | None = None
        for move in moves:
            board.make_move(move)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.unmake_move()
            if score > best:
                best = score
                best_move = move
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break

        if best <= original_alpha:
            flag = TT_UPPER
        elif best >= beta:
            flag = TT_LOWER
        else:
            flag = TT_EXACT
        self._store(key, depth, flag, to_tt_score(best, ply), best_move)
        return best

    def _quiesce(self, board: Board, alpha: int, beta: int, ply: int) -> int:
        """Resolve captures until the position is quiet, then evaluate.

        Not in check: the side to move may "stand pat" (keep the static score),
        so only captures that improve on it are searched, best captures first.
        In check: standing pat is illegal, so every legal evasion is searched and
        no evasions means mate. Stalemate is not detected here (stand-pat is
        used), a standard shortcut.
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

        self._check_stopped()
        order_moves(board, moves)
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
    nodes_limit: int | None = None,
    stop_event: Event | None = None,
    rng: random.Random | None = None,
) -> SearchResult:
    """Convenience wrapper: one-off search with a fresh (empty) transposition table."""
    return Searcher().search(
        board,
        depth=depth,
        movetime_ms=movetime_ms,
        nodes_limit=nodes_limit,
        stop_event=stop_event,
        rng=rng,
    )
