"""Opening definitions and validated opening-file loading for tools.match."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chess


BUILTIN_SET_NAME = "builtin-mini-8"

BUILTIN_OPENINGS = (
    ("Ruy Lopez", "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6"),
    ("Sicilian", "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6"),
    ("Queen's Gambit Declined", "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6"),
    ("King's Indian", "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7"),
    ("French", "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6"),
    ("Caro-Kann", "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4 c3e4 c8f5"),
    ("Reti", "g1f3 d7d5 g2g3 g8f6 f1g2 e7e6"),
    ("English", "c2c4 e7e5 b1c3 g8f6 g1f3 b8c6"),
)

@dataclass(frozen=True)
class Opening:
    name: str
    start_fen: str | None
    moves: tuple[str, ...]

def builtin_openings() -> list[Opening]:
    return [
        Opening(name=f"{name}: {line}", start_fen=None, moves=tuple(line.split()))
        for name, line in BUILTIN_OPENINGS
    ]

def load_openings(path: Path) -> tuple[str, list[Opening]]:
    """Read an opening file: one FEN/EPD or one line of UCI moves per row.

    Blank lines and lines starting with ``#`` are skipped. Returns (set name, openings).
    """
    openings: list[Opening] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        tokens = text.split()
        if "/" in tokens[0]:
            if len(tokens) >= 6 and tokens[4].isdigit() and tokens[5].isdigit():
                fen = " ".join(tokens[:6])
            else:
                fen = " ".join(tokens[:4]) + " 0 1"
            try:
                chess.Board(fen)
            except ValueError as error:
                raise ValueError(f"{path}:{number}: invalid FEN ({error})") from error
            openings.append(Opening(name=text, start_fen=fen, moves=()))
        else:
            board = chess.Board()
            for token in tokens:
                try:
                    board.push_uci(token)
                except ValueError as error:
                    raise ValueError(f"{path}:{number}: illegal opening move {token!r}") from error
            openings.append(Opening(name=text, start_fen=None, moves=tuple(tokens)))
    if not openings:
        raise ValueError(f"{path}: no openings found")
    return path.stem, openings
