"""Negamax search with alpha-beta pruning, quiescence, move ordering, a
transposition table and forward pruning (Stage 6).

Features:
- Root iterative deepening up to ``depth``. With ``movetime_ms`` the search does
  not start an iteration it is very unlikely to finish. If an iteration is
  interrupted after at least one root move was searched, the best root move
  found so far is used (the previous best move is searched first, so any move
  that replaced it was fully searched and scored higher at the new depth);
  ``SearchResult.depth`` still reports only the last *completed* iteration. If
  the first iteration is interrupted before any move finished, the best-ordered
  legal move is returned with depth 0 and no fabricated eval.
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
- Killer moves (two quiet moves per ply that caused a beta cutoff) and a history
  table (quiet moves that caused cutoffs anywhere) improve quiet-move ordering.
- Null-move pruning (non-PV nodes, not in check, side has non-pawn material):
  if passing the turn still fails high at reduced depth, the node is cut.
- Late move reductions: late quiet moves are searched one ply shallower in a
  zero window first and re-searched at full depth only if they beat alpha.
- Each heuristic can be switched off on the ``Searcher`` for tests and debugging.

``SearchResult.depth`` is the depth of the last completed iteration, so it is an
honest measurement: 0 means not even depth 1 finished (a legal move is still
returned).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from threading import Event

from engine.board import BISHOP, DATACLASS_SLOTS, KNIGHT, PAWN, QUEEN, ROOK, Board, Move
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
# A new iteration costs roughly 2-3x the previous one. If less than this
# multiple of the last iteration's time remains, do not start another. It is
# deliberately low (the 0.6.0 SPRT showed engines using only ~70% of their
# time at 3.0): an interrupted iteration is not wasted, because its best move
# so far is used (see ``Searcher.search``).
NEXT_ITERATION_FACTOR = 1.5

# Transposition table.
DEFAULT_HASH_MB = 16
# Rough capacity per megabyte of the UCI Hash option (Python tuples and a dict
# are far bigger than a C table entry, so this is an approximation).
TT_ENTRIES_PER_MB = 5000
TT_EXACT = 0
TT_LOWER = 1  # The true score is at least the stored score (a beta cutoff).
TT_UPPER = 2  # The true score is at most the stored score (all moves failed low).
MATE_BOUND = MATE_SCORE - 1000

# Forward pruning and ordering heuristics (Stage 6).
NULL_MOVE_MIN_DEPTH = 3
NULL_MOVE_REDUCTION = 2
LMR_MIN_DEPTH = 3
LMR_FULL_DEPTH_MOVES = 3  # The first moves of a node are never reduced.
# A checked node searches one ply deeper, at most this many times per line.
MAX_CHECK_EXTENSIONS = 1
# Late move pruning: at the last full ply, quiet moves after this many are skipped.
LMP_MAX_DEPTH = 1
LMP_QUIET_MOVE_LIMIT = 10
KILLER_BONUS = (800, 790)
HISTORY_CAP = 400


@dataclass(**DATACLASS_SLOTS)
class SearchResult:
    best_move: Move | None
    score: int | None
    depth: int  # last fully completed iteration (0 = none, or no search was needed)
    nodes: int
    time_ms: int
    mate: int | None  # positive = we mate in N, negative = we are mated in N
    # Deepest iteration that was started (it may have been cut short, in which case
    # its best root move so far can be the one played). Equals ``depth`` when the
    # last iteration finished.
    attempted_depth: int = 0


class _SearchStopped(Exception):
    """Raised internally when a soft time limit is hit."""


# -- move ordering ----------------------------------------------------------


def _move_score(
    board: Board,
    move: Move,
    killers: tuple[Move, ...] = (),
    history: dict[tuple[int, int], int] | None = None,
) -> int:
    """Ordering score: captures (MVV-LVA) > killers > promotions > quiet moves.

    Quiet moves are ranked by history (cutoff count) plus a small piece-square gain.
    """
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
        if killers:
            if move == killers[0]:
                score += KILLER_BONUS[0]
            elif len(killers) > 1 and move == killers[1]:
                score += KILLER_BONUS[1]
        if history:
            bonus = history.get((moving_piece, move.to_square))
            if bonus:
                score += min(bonus, HISTORY_CAP)
    if move.promotion is not None:
        score += 600 + move.promotion
    return score


def order_moves(
    board: Board,
    moves: list[Move],
    first: Move | None = None,
    killers: tuple[Move, ...] = (),
    history: dict[tuple[int, int], int] | None = None,
) -> None:
    """Sort ``moves`` in place, best first; ``first`` (e.g. the TT move) goes to the front.

    The sort is stable, so equal scores keep the generator's order and the
    result is deterministic.
    """
    moves.sort(key=lambda move: _move_score(board, move, killers, history), reverse=True)
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


def _has_non_pawn_material(board: Board, color: int) -> bool:
    """True if ``color`` has a knight, bishop, rook or queen (guards against zugzwang)."""
    pieces = board.piece_squares
    return any(pieces[color * piece_type] for piece_type in (KNIGHT, BISHOP, ROOK, QUEEN))


class Searcher:
    """Stateful searcher: node counts, stop flags, the transposition table and
    the killer/history tables."""

    def __init__(
        self,
        hash_mb: int = DEFAULT_HASH_MB,
        *,
        null_move: bool = True,
        lmr: bool = True,
        killers: bool = True,
        pvs: bool = False,
        check_extension: bool = False,
        lmp: bool = False,
        next_iteration_factor: float = NEXT_ITERATION_FACTOR,
    ) -> None:
        self.use_pvs = pvs
        self.use_check_extension = check_extension
        self.use_lmp = lmp
        self.next_iteration_factor = next_iteration_factor
        self.use_null_move = null_move
        self.use_lmr = lmr
        self.use_killers = killers
        self._killers: list[tuple[Move, ...]] = [()] * (MAX_PLY + 2)
        self._history: dict[tuple[int, int], int] = {}
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
        self._killers = [()] * (MAX_PLY + 2)
        self._history = {}

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
        attempted_depth = 0

        for iteration in range(1, depth + 1):
            iteration_started = time.monotonic()
            attempted_depth = iteration
            try:
                move, score = self._search_root(board, moves, iteration, rng)
            except _SearchStopped:
                if self._partial is not None:
                    # Interrupted iteration: its best root move so far was searched
                    # fully at this depth and beat every move tried before it
                    # (including the previous best, which is searched first).
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
                if remaining <= 0 or remaining < last_iteration * self.next_iteration_factor:
                    break

        return self._result(best_move, best_score, completed_depth, started, attempted_depth)

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

    def _result(
        self,
        move: Move | None,
        score: int | None,
        depth: int,
        started: float,
        attempted_depth: int | None = None,
    ) -> SearchResult:
        return SearchResult(
            best_move=move,
            score=score,
            depth=depth,
            nodes=self.nodes,
            time_ms=int((time.monotonic() - started) * 1000),
            mate=None if score is None else _mate_distance(score),
            attempted_depth=depth if attempted_depth is None else attempted_depth,
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

    def _negamax(
        self,
        board: Board,
        depth: int,
        alpha: int,
        beta: int,
        ply: int,
        allow_null: bool = True,
        extensions: int = 0,
    ) -> int:
        if depth <= 0:
            return self._quiesce(board, alpha, beta, ply)

        self._count_node()
        if board.is_fifty_move_draw():
            return self._fifty_move_score(board, ply)
        if board.is_threefold_repetition() or board.is_insufficient_material():
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

        in_check = board.in_check()
        if (
            self.use_check_extension
            and in_check
            and extensions < MAX_CHECK_EXTENSIONS
            and ply < MAX_PLY - 2
        ):
            depth += 1
            extensions += 1

        # Null-move pruning: if passing the turn still scores >= beta at reduced
        # depth, this node would almost certainly fail high anyway. Only in
        # non-PV (zero-width-ish) windows, never in check, never with just
        # king and pawns (zugzwang), and never twice in a row.
        if (
            self.use_null_move
            and allow_null
            and depth >= NULL_MOVE_MIN_DEPTH
            and not in_check
            and beta - alpha == 1
            and abs(beta) < MATE_BOUND
            and _has_non_pawn_material(board, board.side_to_move)
        ):
            board.make_null_move()
            try:
                null_score = -self._negamax(
                    board,
                    depth - 1 - NULL_MOVE_REDUCTION,
                    -beta,
                    -beta + 1,
                    ply + 1,
                    False,
                    extensions=extensions,
                )
            finally:
                board.unmake_null_move()
            if null_score >= beta:
                return beta if null_score >= MATE_BOUND else null_score

        moves = list(generate_legal_moves(board, known_in_check=in_check))
        self._check_stopped()
        if not moves:
            return self._terminal_score(board, ply)
        killers = self._killers[ply] if self.use_killers and ply < len(self._killers) else ()
        order_moves(board, moves, tt_move, killers, self._history if self.use_killers else None)

        original_alpha = alpha
        best = -MATE_SCORE
        best_move: Move | None = None
        squares = board.squares
        for index, move in enumerate(moves):
            moving_piece = squares[move.from_square]
            is_quiet = (
                squares[move.to_square] == 0
                and move.promotion is None
                and not (abs(moving_piece) == PAWN and (move.from_square & 7) != (move.to_square & 7))
            )
            board.make_move(move)
            try:
                if (
                    self.use_lmp
                    and not in_check
                    and depth <= LMP_MAX_DEPTH
                    and index >= LMP_QUIET_MOVE_LIMIT
                    and is_quiet
                    and abs(beta) < MATE_BOUND
                    and not board.in_check()
                ):
                    continue
                reduce = (
                    self.use_lmr
                    and is_quiet
                    and index >= LMR_FULL_DEPTH_MOVES
                    and depth >= LMR_MIN_DEPTH
                    and not in_check
                    and not board.in_check()
                )
                if self.use_pvs and index > 0:
                    # Principal variation search: the first move is searched with the
                    # full window; every later move is first tried with a zero window
                    # (cheap, and what lets null-move pruning run below it), and only a
                    # move that raises alpha without reaching beta is searched again
                    # with the full window to get its exact score.
                    score = -self._negamax(
                        board,
                        depth - 2 if reduce else depth - 1,
                        -alpha - 1,
                        -alpha,
                        ply + 1,
                        extensions=extensions,
                    )
                    if reduce and score > alpha:
                        score = -self._negamax(
                            board, depth - 1, -alpha - 1, -alpha, ply + 1, extensions=extensions
                        )
                    if alpha < score < beta:
                        score = -self._negamax(
                            board, depth - 1, -beta, -alpha, ply + 1, extensions=extensions
                        )
                elif reduce:
                    # Late quiet move: look one ply shallower with a zero window first.
                    score = -self._negamax(
                        board, depth - 2, -alpha - 1, -alpha, ply + 1, extensions=extensions
                    )
                    if score > alpha:
                        score = -self._negamax(
                            board, depth - 1, -beta, -alpha, ply + 1, extensions=extensions
                        )
                else:
                    score = -self._negamax(
                        board, depth - 1, -beta, -alpha, ply + 1, extensions=extensions
                    )
            finally:
                board.unmake_move()
            if score > best:
                best = score
                best_move = move
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if is_quiet:
                    self._record_cutoff(move, moving_piece, depth, ply)
                break

        if best <= original_alpha:
            flag = TT_UPPER
        elif best >= beta:
            flag = TT_LOWER
        else:
            flag = TT_EXACT
        self._store(key, depth, flag, to_tt_score(best, ply), best_move)
        return best

    def _record_cutoff(self, move: Move, moving_piece: int, depth: int, ply: int) -> None:
        """Remember a quiet move that caused a beta cutoff (killer + history)."""
        if not self.use_killers:
            return
        if ply < len(self._killers):
            current = self._killers[ply]
            if not current or current[0] != move:
                self._killers[ply] = (move, current[0]) if current else (move,)
        key = (moving_piece, move.to_square)
        self._history[key] = self._history.get(key, 0) + depth * depth

    def _quiesce(self, board: Board, alpha: int, beta: int, ply: int) -> int:
        """Resolve captures until the position is quiet, then evaluate.

        Not in check: the side to move may "stand pat" (keep the static score),
        so only captures that improve on it are searched, best captures first.
        In check: standing pat is illegal, so every legal evasion is searched and
        no evasions means mate. Stalemate is not detected here (stand-pat is
        used), a standard shortcut.
        """
        self._count_node()
        if board.is_fifty_move_draw():
            return self._fifty_move_score(board, ply)
        if board.is_threefold_repetition() or board.is_insufficient_material():
            return DRAW_SCORE
        if ply >= MAX_PLY:
            return evaluate(board)

        if board.in_check():
            moves = list(generate_legal_moves(board, known_in_check=True))
            if not moves:
                return -MATE_SCORE + ply
            best = -MATE_SCORE + ply
        else:
            best = evaluate(board)
            if best >= beta:
                return best
            if best > alpha:
                alpha = best
            moves = list(generate_legal_moves(board, captures_only=True, known_in_check=False))

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
    def _fifty_move_score(board: Board, ply: int) -> int:
        """Score of a position whose halfmove clock reached 100.

        A checkmate on the 100th half-move still wins: the fifty-move rule cannot
        be claimed once the game is over. Only runs when the clock is that high,
        so the legal-move check costs nothing in normal search.
        """
        if board.is_checkmate():
            return -MATE_SCORE + ply
        return DRAW_SCORE

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
