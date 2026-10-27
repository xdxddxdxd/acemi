"""Classical material evaluation (Stage 3).

Piece values follow the conventional centipawn scale. There are no piece-square
tables, pawn-structure terms, or king-safety terms yet; those arrive in later
stages. The score is always from the side to move's perspective.
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

# Conventional centipawn values. King is large so material imbalance never
# outweighs mate scores (mate uses 100_000 in search).
PIECE_VALUE = {
    PAWN: 100,
    KNIGHT: 320,
    BISHOP: 330,
    ROOK: 500,
    QUEEN: 900,
    KING: 20_000,
}


def evaluate_classic(board: Board) -> int:
    """Material balance in centipawns, side-to-move positive."""
    score = 0
    for piece, squares in board.piece_squares.items():
        if not squares:
            continue
        value = PIECE_VALUE[abs(piece)]
        if piece > 0:
            score += value * len(squares)
        else:
            score -= value * len(squares)
    # Convert white-centric score to side-to-move perspective.
    return score if board.side_to_move == WHITE else -score
