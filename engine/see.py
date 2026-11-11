"""Material-only static exchange estimate for move ordering, never pruning.

Swap off least valuable legal attackers on one square. Occupancy is private:
pins, king recaptures, x-rays, en passant and promotion do not mutate Board.
This is an ordering heuristic, not a tactical oracle (off-square moves and
alternative equal-value attacker choices are not searched).
"""

from __future__ import annotations

from engine.board import BISHOP, KING, KNIGHT, PAWN, QUEEN, ROOK, Board, Move
from engine.eval.classic import PIECE_VALUE

_KNIGHTS = (-33, -31, -18, -14, 14, 18, 31, 33)
_KINGS = (-17, -16, -15, -1, 1, 15, 16, 17)
_RAYS = ((-17, BISHOP), (-15, BISHOP), (15, BISHOP), (17, BISHOP),
         (-16, ROOK), (-1, ROOK), (1, ROOK), (16, ROOK))


def _attackers(squares: list[int], target: int, color: int):
    for delta in (15 * color, 17 * color):
        source = target + delta
        if 0 <= source < 128 and not source & 0x88 and squares[source] == color * PAWN:
            yield source
    for delta in _KNIGHTS:
        source = target + delta
        if 0 <= source < 128 and not source & 0x88 and squares[source] == color * KNIGHT:
            yield source
    for delta, slider in _RAYS:
        source = target + delta
        while 0 <= source < 128 and not source & 0x88:
            piece = squares[source]
            if piece:
                if piece == color * slider or piece == color * QUEEN:
                    yield source
                break
            source += delta
    for delta in _KINGS:
        source = target + delta
        if 0 <= source < 128 and not source & 0x88 and squares[source] == color * KING:
            yield source


def _least_attacker(squares: list[int], target: int, color: int, king: int) -> int | None:
    candidates = sorted(_attackers(squares, target, color),
                        key=lambda source: (PIECE_VALUE[abs(squares[source])], source))
    victim = squares[target]
    for source in candidates:
        piece = squares[source]
        squares[source], squares[target] = 0, piece
        own_king = target if abs(piece) == KING else king
        legal = next(_attackers(squares, own_king, -color), None) is None
        squares[source], squares[target] = piece, victim
        if legal:
            return source
    return None


def static_exchange(board: Board, move: Move) -> int:
    """Estimate the material gain in cp of an already legal tactical move.

    The initial move is forced. Subsequent sides may decline the exchange.
    Recapturing pawns on the back rank are estimated as queen promotions;
    the initial move's actual promotion type is always respected.
    """
    squares = board.squares.copy()
    target = move.to_square
    moving = squares[move.from_square]
    color = 1 if moving > 0 else -1
    captured = squares[target]
    if (abs(moving) == PAWN and target == board.en_passant_square
            and (move.from_square & 7) != (target & 7) and not captured):
        captured_square = target + 16 * color
        captured = squares[captured_square]
        squares[captured_square] = 0
    gains = [PIECE_VALUE[abs(captured)] if captured else 0]
    placed = color * move.promotion if move.promotion is not None else moving
    if move.promotion is not None:
        gains[0] += PIECE_VALUE[move.promotion] - PIECE_VALUE[PAWN]
    squares[move.from_square], squares[target] = 0, placed
    kings = dict(board.king_squares)
    if abs(moving) == KING:
        kings[color] = target
    side = -color
    while abs(squares[target]) != KING:
        source = _least_attacker(squares, target, side, kings[side])
        if source is None:
            break
        piece = squares[source]
        promoted = abs(piece) == PAWN and (target >> 4) in (0, 7)
        bonus = PIECE_VALUE[QUEEN] - PIECE_VALUE[PAWN] if promoted else 0
        gains.append(PIECE_VALUE[abs(squares[target])] + bonus - gains[-1])
        squares[source], squares[target] = 0, side * QUEEN if promoted else piece
        if abs(piece) == KING:
            kings[side] = target
        side = -side
    for index in range(len(gains) - 1, 0, -1):
        gains[index - 1] = min(gains[index - 1], -gains[index])
    return gains[0]
