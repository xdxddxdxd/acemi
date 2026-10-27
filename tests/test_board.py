"""Board-state and special-rule tests for Stage 1."""

import unittest

from engine.board import (
    BLACK,
    WHITE,
    Board,
    STARTING_FEN,
)
from engine.movegen import find_legal_move, generate_legal_moves
from tests.test_perft import KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6


class BoardStateTests(unittest.TestCase):
    def test_fen_round_trip_for_reference_positions(self) -> None:
        for fen in (STARTING_FEN, KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6):
            with self.subTest(fen=fen):
                board = Board(fen)
                self.assertEqual(Board(board.to_fen()).to_fen(), board.to_fen())

    def test_incremental_hash_and_unmake_for_every_start_move(self) -> None:
        board = Board()
        original_fen = board.to_fen()
        original_hash = board.zobrist_hash
        for move in list(generate_legal_moves(board)):
            board.make_move(move)
            self.assertEqual(board.zobrist_hash, board.compute_zobrist_hash(), move.uci())
            board.unmake_move()
            self.assertEqual(board.to_fen(), original_fen, move.uci())
            self.assertEqual(board.zobrist_hash, original_hash, move.uci())
            self.assertEqual(board.zobrist_hash, board.compute_zobrist_hash(), move.uci())

    def test_castling_and_undo(self) -> None:
        board = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        before = board.to_fen()
        for uci in ("e1g1", "e1c1"):
            move = find_legal_move(board, uci)
            board.make_move(move)
            self.assertEqual(board.side_to_move, BLACK)
            self.assertEqual(board.zobrist_hash, board.compute_zobrist_hash())
            board.unmake_move()
            self.assertEqual(board.to_fen(), before)

    def test_castling_through_attacked_square_is_illegal(self) -> None:
        board = Board("5r1k/8/8/8/8/8/8/4K2R w K - 0 1")
        self.assertNotIn("e1g1", {move.uci() for move in generate_legal_moves(board)})

    def test_en_passant_and_undo(self) -> None:
        board = Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2")
        before = board.to_fen()
        board.make_move(find_legal_move(board, "e5d6"))
        self.assertEqual(board.piece_at(51), 0)  # d5 pawn was captured.
        self.assertEqual(board.piece_at(35), WHITE)  # White pawn landed on d6.
        self.assertEqual(board.piece_at(52), 0)  # e5 is now empty.
        self.assertEqual(board.zobrist_hash, board.compute_zobrist_hash())
        board.unmake_move()
        self.assertEqual(board.to_fen(), before)

    def test_illegal_en_passant_cannot_expose_king(self) -> None:
        board = Board("k3r3/8/8/3pP3/8/8/8/4K3 w - d6 0 2")
        legal = {move.uci() for move in generate_legal_moves(board)}
        self.assertNotIn("e5d6", legal)

    def test_all_four_promotion_choices_for_push_and_capture(self) -> None:
        board = Board("1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        moves = {move.uci() for move in generate_legal_moves(board)}
        self.assertTrue({"a7a8q", "a7a8r", "a7a8b", "a7a8n"}.issubset(moves))
        self.assertTrue({"a7b8q", "a7b8r", "a7b8b", "a7b8n"}.issubset(moves))
        for uci in ("a7a8q", "a7a8r", "a7a8b", "a7a8n"):
            move = find_legal_move(board, uci)
            before = board.to_fen()
            board.make_move(move)
            self.assertEqual(board.piece_at(0), {"q": 5, "r": 4, "b": 3, "n": 2}[uci[-1]])
            self.assertEqual(board.zobrist_hash, board.compute_zobrist_hash())
            board.unmake_move()
            self.assertEqual(board.to_fen(), before)

    def test_threefold_repetition(self) -> None:
        board = Board()
        cycle = ("g1f3", "g8f6", "f3g1", "f6g8")
        for uci in cycle * 2:
            board.make_move(find_legal_move(board, uci))
        self.assertTrue(board.is_threefold_repetition())
        self.assertEqual(board.zobrist_hash, board.compute_zobrist_hash())

    def test_fifty_move_rule(self) -> None:
        board = Board("4k3/8/8/8/8/8/8/4K2R w - - 99 1")
        board.make_move(find_legal_move(board, "h1h2"))
        self.assertTrue(board.is_fifty_move_draw())

    def test_insufficient_material(self) -> None:
        cases = (
            "4k3/8/8/8/8/8/8/4K3 w - - 0 1",
            "4k3/8/8/8/8/8/8/4KB2 w - - 0 1",
            "4k3/8/8/8/8/8/8/4KN2 w - - 0 1",
            "4k3/8/8/8/8/8/1B6/2B1K3 w - - 0 1",
        )
        for fen in cases:
            with self.subTest(fen=fen):
                self.assertTrue(Board(fen).is_insufficient_material())
        self.assertFalse(Board("1n2k3/8/8/8/8/8/8/2B1K3 w - - 0 1").is_insufficient_material())


if __name__ == "__main__":
    unittest.main()
