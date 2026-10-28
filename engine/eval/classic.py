"""Classical evaluation: material + piece-square tables, tapered (Stage 4).

Piece-square tables are the widely used "Simplified Evaluation Function"
tables (Tomasz Michniewski). Knights, bishops, rooks and queens use the same
table in the opening and the endgame; pawns and kings have separate endgame
tables (advanced pawns are worth more, the king belongs in the centre). The
two scores are blended by a game phase computed from the remaining non-pawn
material, so the evaluation moves smoothly from opening to endgame.

Tables are written from White's point of view with rank 8 on the first row,
which is exactly the row order of the 0x88 board (``square >> 4`` is the row).
Black pieces use the vertically mirrored row. Because the king's endgame table
rewards the centre, the opponent's king is pushed toward the edge when we are
ahead, which is what lets the engine finish won endgames.

The score is always from the side to move's perspective.
"""

from __future__ import annotations

from engine.board import (
    BISHOP,
    KING,
    KNIGHT,
    PAWN,
    QUEEN,
    ROOK,
    WHITE,
    Board,
)

# Conventional centipawn values, kept for tests and other modules. Kings carry
# no material term (both sides always have exactly one, so it would cancel).
PIECE_VALUE = {
    PAWN: 100,
    KNIGHT: 320,
    BISHOP: 330,
    ROOK: 500,
    QUEEN: 900,
    KING: 20_000,
}
MATERIAL = {PAWN: 100, KNIGHT: 320, BISHOP: 330, ROOK: 500, QUEEN: 900, KING: 0}

# Game phase: knights/bishops 1, rooks 2, queens 4 (24 = full opening material).
PHASE_WEIGHT = {PAWN: 0, KNIGHT: 1, BISHOP: 1, ROOK: 2, QUEEN: 4, KING: 0}
MAX_PHASE = 24

_PAWN_MG = (
    0, 0, 0, 0, 0, 0, 0, 0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
    5, 5, 10, 25, 25, 10, 5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, -5, -10, 0, 0, -10, -5, 5,
    5, 10, 10, -20, -20, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
)
_PAWN_EG = (
    0, 0, 0, 0, 0, 0, 0, 0,
    80, 80, 80, 80, 80, 80, 80, 80,
    50, 50, 50, 50, 50, 50, 50, 50,
    30, 30, 30, 30, 30, 30, 30, 30,
    20, 20, 20, 20, 20, 20, 20, 20,
    10, 10, 10, 10, 10, 10, 10, 10,
    5, 5, 5, 5, 5, 5, 5, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
)
_KNIGHT = (
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
)
_BISHOP = (
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
)
_ROOK = (
    0, 0, 0, 0, 0, 0, 0, 0,
    5, 10, 10, 10, 10, 10, 10, 5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    0, 0, 0, 5, 5, 0, 0, 0,
)
_QUEEN = (
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -5, 0, 5, 5, 5, 5, 0, -5,
    0, 0, 5, 5, 5, 5, 0, -5,
    -10, 5, 5, 5, 5, 5, 0, -10,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
)
_KING_MG = (
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20,
)
_KING_EG = (
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
)

# Material and table folded together: [piece type] -> 64 values (middlegame / endgame).
_MG_TABLE = {
    PAWN: _PAWN_MG,
    KNIGHT: _KNIGHT,
    BISHOP: _BISHOP,
    ROOK: _ROOK,
    QUEEN: _QUEEN,
    KING: _KING_MG,
}
_EG_TABLE = {
    PAWN: _PAWN_EG,
    KNIGHT: _KNIGHT,
    BISHOP: _BISHOP,
    ROOK: _ROOK,
    QUEEN: _QUEEN,
    KING: _KING_EG,
}


def _build_square_values(tables: dict[int, tuple[int, ...]]) -> dict[int, list[int]]:
    """Per signed piece: value (material + table) for each of the 128 0x88 squares."""
    values: dict[int, list[int]] = {}
    for piece_type, table in tables.items():
        white = [0] * 128
        black = [0] * 128
        for square in range(128):
            if square & 0x88:
                continue
            row, col = square >> 4, square & 7
            white[square] = MATERIAL[piece_type] + table[row * 8 + col]
            black[square] = MATERIAL[piece_type] + table[(7 - row) * 8 + col]
        values[piece_type] = white
        values[-piece_type] = black
    return values


_MG_VALUES = _build_square_values(_MG_TABLE)
_EG_VALUES = _build_square_values(_EG_TABLE)


def evaluate_classic(board: Board) -> int:
    """Tapered material + piece-square score in centipawns, side-to-move positive."""
    mg = 0
    eg = 0
    phase = 0
    for piece, squares in board.piece_squares.items():
        if not squares:
            continue
        mg_values = _MG_VALUES[piece]
        eg_values = _EG_VALUES[piece]
        sign = 1 if piece > 0 else -1
        for square in squares:
            mg += sign * mg_values[square]
            eg += sign * eg_values[square]
        phase += PHASE_WEIGHT[abs(piece)] * len(squares)

    if phase > MAX_PHASE:
        phase = MAX_PHASE  # Promotions can push the total above the opening maximum.
    blended = mg * phase + eg * (MAX_PHASE - phase)
    # Divide toward zero so the score is exactly antisymmetric between colours.
    score = blended // MAX_PHASE if blended >= 0 else -((-blended) // MAX_PHASE)
    return score if board.side_to_move == WHITE else -score
