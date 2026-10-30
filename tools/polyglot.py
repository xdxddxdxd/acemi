"""Polyglot writer helpers (tools only)."""

from __future__ import annotations

import struct
from pathlib import Path

import chess

_PROMOTION = {chess.KNIGHT: 1, chess.BISHOP: 2, chess.ROOK: 3, chess.QUEEN: 4}


def encode_move(board: chess.Board, move: chess.Move) -> int:
    """Encode a python-chess move in the 16-bit Polyglot format."""
    if board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        to_square = chess.square(7 if chess.square_file(move.to_square) > 4 else 0, rank)
    else:
        to_square = move.to_square
    from_file = chess.square_file(move.from_square)
    from_rank = chess.square_rank(move.from_square)
    to_file = chess.square_file(to_square)
    to_rank = chess.square_rank(to_square)
    promotion = _PROMOTION.get(move.promotion, 0)
    return (
        (promotion << 12)
        | (from_rank << 9)
        | (from_file << 6)
        | (to_rank << 3)
        | to_file
    )


def write_book(path: Path, entries: dict[int, dict[int, int]]) -> None:
    """Write ``{key: {encoded_move: weight}}`` as a Polyglot book."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        for key in sorted(entries):
            for move, weight in sorted(entries[key].items()):
                stream.write(struct.pack(">QHHI", key, move, weight, 0))
        stream.write(b"\0" * 16)
