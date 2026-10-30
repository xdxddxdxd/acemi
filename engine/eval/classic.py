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


def pst_delta(piece: int, from_square: int, to_square: int) -> int:
    """Middlegame piece-square gain of moving ``piece`` (signed) between two squares.

    Used only to order quiet moves; it is cheap and needs no board.
    """
    values = _MG_VALUES[piece]
    return values[to_square] - values[from_square]


class EvalFlags:
    """Stage 7 evaluation features. Every one is off until a match proves it helps.

    One engine process has one set of flags (UCI ``setoption`` changes them), so a
    single build can play itself with a feature on and off for an A/B test.
    """

    __slots__ = ("passed_pawns", "pawn_structure", "bishop_pair", "king_safety")

    def __init__(self) -> None:
        self.passed_pawns = False
        self.pawn_structure = False
        self.bishop_pair = False
        self.king_safety = False


FLAGS = EvalFlags()

# Passed pawn bonus by relative rank (0 = own back rank, 6 = one step from promotion).
_PASSED_MG = (0, 5, 8, 15, 28, 50, 80, 0)
_PASSED_EG = (0, 10, 18, 35, 65, 110, 170, 0)


def _passed_pawn_bonus(board: Board) -> tuple[int, int]:
    """(middlegame, endgame) passed pawn bonus, White minus Black.

    A pawn is passed when no enemy pawn stands ahead of it on its own or a
    neighbouring file. The bonus grows with how far it has advanced.
    """
    white_pawns = board.piece_squares[PAWN]
    black_pawns = board.piece_squares[-PAWN]
    if not white_pawns and not black_pawns:
        return 0, 0
    # Most advanced enemy pawn per file: black's smallest row, white's largest row.
    black_min = [8] * 8
    for square in black_pawns:
        file, row = square & 7, square >> 4
        if row < black_min[file]:
            black_min[file] = row
    white_max = [-1] * 8
    for square in white_pawns:
        file, row = square & 7, square >> 4
        if row > white_max[file]:
            white_max[file] = row

    mg = 0
    eg = 0
    for square in white_pawns:
        file, row = square & 7, square >> 4
        if black_min[file] < row:
            continue
        if file > 0 and black_min[file - 1] < row:
            continue
        if file < 7 and black_min[file + 1] < row:
            continue
        rank = 7 - row
        mg += _PASSED_MG[rank]
        eg += _PASSED_EG[rank]
    for square in black_pawns:
        file, row = square & 7, square >> 4
        if white_max[file] > row:
            continue
        if file > 0 and white_max[file - 1] > row:
            continue
        if file < 7 and white_max[file + 1] > row:
            continue
        rank = row
        mg -= _PASSED_MG[rank]
        eg -= _PASSED_EG[rank]
    return mg, eg


# Pawn structure penalties (isolated, doubled, backward) and the bishop pair bonus.
_ISOLATED_MG = 15
_ISOLATED_EG = 10
_DOUBLED_MG = 12
_DOUBLED_EG = 20
_BACKWARD_MG = 10
_BACKWARD_EG = 10
_BISHOP_PAIR_MG = 20
_BISHOP_PAIR_EG = 30
_KING_OPEN_PENALTY_MG = 12


def _pawn_structure(board: Board) -> tuple[int, int]:
    """(middlegame, endgame) pawn structure penalty, White minus Black.

    Isolated: no friendly pawn on a neighbouring file. Doubled: every pawn beyond
    the first on a file. Backward: there are friendly pawns on neighbouring files
    but all of them are more advanced, so this pawn cannot be supported. An
    isolated pawn is not also charged as backward.
    """
    white = board.piece_squares[PAWN]
    black = board.piece_squares[-PAWN]
    if not white and not black:
        return 0, 0
    white_files: list[list[int]] = [[] for _ in range(8)]
    black_files: list[list[int]] = [[] for _ in range(8)]
    for square in white:
        white_files[square & 7].append(square >> 4)
    for square in black:
        black_files[square & 7].append(square >> 4)

    mg = 0
    eg = 0
    for file in range(8):
        extra_white = len(white_files[file]) - 1
        if extra_white > 0:
            mg -= _DOUBLED_MG * extra_white
            eg -= _DOUBLED_EG * extra_white
        extra_black = len(black_files[file]) - 1
        if extra_black > 0:
            mg += _DOUBLED_MG * extra_black
            eg += _DOUBLED_EG * extra_black

    for square in white:
        file, row = square & 7, square >> 4
        neighbours = (white_files[file - 1] if file > 0 else []) + (white_files[file + 1] if file < 7 else [])
        if not neighbours:
            mg -= _ISOLATED_MG
            eg -= _ISOLATED_EG
        elif all(neighbour_row < row for neighbour_row in neighbours):
            mg -= _BACKWARD_MG
            eg -= _BACKWARD_EG
    for square in black:
        file, row = square & 7, square >> 4
        neighbours = (black_files[file - 1] if file > 0 else []) + (black_files[file + 1] if file < 7 else [])
        if not neighbours:
            mg += _ISOLATED_MG
            eg += _ISOLATED_EG
        elif all(neighbour_row > row for neighbour_row in neighbours):
            mg += _BACKWARD_MG
            eg += _BACKWARD_EG
    return mg, eg


def _bishop_pair_bonus(board: Board) -> tuple[int, int]:
    """(middlegame, endgame) bonus for owning two bishops, White minus Black."""
    mg = 0
    eg = 0
    if len(board.piece_squares[BISHOP]) >= 2:
        mg += _BISHOP_PAIR_MG
        eg += _BISHOP_PAIR_EG
    if len(board.piece_squares[-BISHOP]) >= 2:
        mg -= _BISHOP_PAIR_MG
        eg -= _BISHOP_PAIR_EG
    return mg, eg


def _king_safety(board: Board) -> tuple[int, int]:
    """(middlegame, endgame) king safety penalty, White minus Black.

    Only applies while queens are on the board and the king is still on its back
    two ranks. A king file (and its two neighbours) without a friendly pawn one or
    two ranks in front of the king is semi-open and gets the penalty. Endgame
    score is zero: a shielded king matters in the middlegame, not the endgame.
    """
    if not board.piece_squares[QUEEN] and not board.piece_squares[-QUEEN]:
        return 0, 0
    mg = 0
    for color, sign in ((WHITE, 1), (-WHITE, -1)):
        king_square = board.king_squares[color]
        row = king_square >> 4
        if color == WHITE and row < 6:
            continue
        if color != WHITE and row > 1:
            continue
        file = king_square & 7
        pawns = board.piece_squares[color * PAWN]
        missing = 0
        for shield_file in (file - 1, file, file + 1):
            if shield_file < 0 or shield_file > 7:
                continue
            shielded = False
            for square in pawns:
                if square & 7 != shield_file:
                    continue
                distance = row - (square >> 4) if color == WHITE else (square >> 4) - row
                if 0 < distance <= 2:
                    shielded = True
                    break
            if not shielded:
                missing += 1
        mg -= sign * _KING_OPEN_PENALTY_MG * missing
    return mg, 0


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

    if FLAGS.passed_pawns:
        bonus_mg, bonus_eg = _passed_pawn_bonus(board)
        mg += bonus_mg
        eg += bonus_eg
    if FLAGS.pawn_structure:
        bonus_mg, bonus_eg = _pawn_structure(board)
        mg += bonus_mg
        eg += bonus_eg
    if FLAGS.bishop_pair:
        bonus_mg, bonus_eg = _bishop_pair_bonus(board)
        mg += bonus_mg
        eg += bonus_eg
    if FLAGS.king_safety:
        bonus_mg, bonus_eg = _king_safety(board)
        mg += bonus_mg
        eg += bonus_eg

    if phase > MAX_PHASE:
        phase = MAX_PHASE  # Promotions can push the total above the opening maximum.
    blended = mg * phase + eg * (MAX_PHASE - phase)
    # Divide toward zero so the score is exactly antisymmetric between colours.
    score = blended // MAX_PHASE if blended >= 0 else -((-blended) // MAX_PHASE)
    return score if board.side_to_move == WHITE else -score
