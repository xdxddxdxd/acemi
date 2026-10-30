"""The fast legal move generator must equal the slow reference, move for move and in order."""

import random
import unittest

from engine.board import Board
from engine.movegen import generate_legal_moves, generate_legal_moves_reference
from tests.test_perft import KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
SPECIAL = (
    # En passant that would expose the king along the rank: illegal.
    "8/8/8/KPp4r/8/8/8/7k w - c6 0 1",
    # Ordinary en passant capture.
    "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1",
    # Knight pinned to its king by a rook: it cannot move at all.
    "4r3/8/8/8/8/8/4N3/4K2k w - - 0 1",
    # Bishop pinned diagonally: it may only move along the pin line.
    "4k3/8/8/8/1b6/8/3B4/4K3 w - - 0 1",
    # Rook pinned on a file may slide along it.
    "4r2k/8/8/8/8/8/4R3/4K3 w - - 0 1",
    # Two own pieces on the same line: neither is pinned.
    "4r2k/8/8/8/8/4N3/4B3/4K3 w - - 0 1",
    # In check from a rook next to the king: capture or step away.
    "4k3/8/8/8/8/8/4r3/4K3 w - - 0 1",
    # Double check: only the king may move.
    "4k3/8/8/8/1b6/3n4/8/4K3 w - - 0 1",
    # Castling both ways, and promotions.
    "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1",
    "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1",
    "8/P6k/8/8/8/8/7p/K7 w - - 0 1",
    "8/P6k/8/8/8/8/7p/K7 b - - 0 1",
    # Checkmate and stalemate: no legal moves.
    "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",
    "7k/5P2/6K1/8/8/8/8/8 b - - 0 1",
)
TREE_ROOTS = (START, KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6)


class LegalMoveEquivalenceTests(unittest.TestCase):
    def assert_same(self, board: Board) -> None:
        fen = board.to_fen()
        in_check = board.in_check()
        for captures_only in (False, True):
            expected = list(generate_legal_moves_reference(board, captures_only))
            self.assertEqual(list(generate_legal_moves(board, captures_only)), expected, fen)
            self.assertEqual(
                list(generate_legal_moves(board, captures_only, known_in_check=in_check)), expected, fen
            )
        # Generating moves must leave the board exactly as it was.
        self.assertEqual(board.to_fen(), fen)

    def walk(self, board: Board, depth: int) -> None:
        self.assert_same(board)
        if depth == 0:
            return
        for move in list(generate_legal_moves_reference(board)):
            board.make_move(move)
            self.walk(board, depth - 1)
            board.unmake_move()

    def test_special_positions(self) -> None:
        for fen in SPECIAL:
            with self.subTest(fen=fen):
                self.walk(Board(fen), 2)

    def test_reference_trees_to_depth_two(self) -> None:
        for fen in TREE_ROOTS:
            with self.subTest(fen=fen):
                self.walk(Board(fen), 2)

    def test_random_playouts(self) -> None:
        rng = random.Random(20261030)
        for fen in (START, KIWIPETE, POSITION_4):
            for _ in range(8):
                board = Board(fen)
                for _ply in range(60):
                    self.assert_same(board)
                    moves = list(generate_legal_moves_reference(board))
                    if not moves:
                        break
                    board.make_move(rng.choice(moves))

    def test_pinned_knight_has_no_moves(self) -> None:
        board = Board("4r3/8/8/8/8/8/4N3/4K2k w - - 0 1")
        moves = {move.uci() for move in generate_legal_moves(board)}
        self.assertFalse(any(uci.startswith("e2") for uci in moves))

    def test_en_passant_that_exposes_the_king_is_rejected(self) -> None:
        board = Board("8/8/8/KPp4r/8/8/8/7k w - c6 0 1")
        self.assertNotIn("b5c6", {move.uci() for move in generate_legal_moves(board)})


if __name__ == "__main__":
    unittest.main()
