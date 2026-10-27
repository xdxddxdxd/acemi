"""Evaluation interface for Acemi.

``evaluate(board)`` returns a centipawn score from the side-to-move's point of
view. Positive means the side to move is better. Classical and future (e.g.
NNUE-style) evaluators share this contract so search never depends on a
specific implementation.
"""

from __future__ import annotations

from engine.board import Board
from engine.eval.classic import evaluate_classic


def evaluate(board: Board) -> int:
    """Return a centipawn evaluation from the side to move's perspective."""
    return evaluate_classic(board)
