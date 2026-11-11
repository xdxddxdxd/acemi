"""King-safety occupancy probes versus full make/unmake and python-chess.

These are single-position move checks, never search/perft/matches.
"""

import copy
import random
import unittest
from unittest.mock import patch

import chess

from engine.board import Board
from engine.movegen import (
    _king_safe_after, generate_legal_moves, generate_legal_moves_reference,
    generate_pseudo_legal_moves,
)
from tests.test_movegen_equivalence import SPECIAL
from tools.bench import POSITIONS

EXTRA = (
    "k3r3/8/8/8/8/8/4r3/4K3 w - - 0 1",  # King cannot capture a protected rook.
    "k7/8/8/8/8/8/r3K3/8 w - - 0 1",  # Vacating the king square reveals the same rook ray.
    "k7/8/8/3pP3/4K3/8/8/8 w - d6 0 1",  # EP removes the checking pawn.
    "b6k/8/8/3pP3/8/8/8/7K w - d6 0 1",  # EP opens a bishop ray toward the king.
    "k5rb/6P1/8/8/8/8/8/6K1 w - - 0 1",  # All capture promotions expose a rook check.
)


class OccupancyProbeTests(unittest.TestCase):
    def test_each_pseudo_move_matches_full_make_unmake(self):
        for original in EXTRA + SPECIAL + tuple(fen for _, fen in POSITIONS):
            for fen in (original, chess.Board(original).mirror().fen()):
                with self.subTest(fen=fen):
                    board = Board(fen)
                    color, king = board.side_to_move, board.king_squares[board.side_to_move]
                    before = copy.deepcopy(board.__dict__)
                    for move in list(generate_pseudo_legal_moves(board)):
                        board.make_move(move)
                        expected = not board.in_check(color)
                        board.unmake_move()
                        self.assertEqual(_king_safe_after(board, move, color, king), expected, move.uci())
                        self.assertEqual(board.__dict__, before)

    def test_legal_moves_match_python_chess_and_reference_order(self):
        for original in EXTRA:
            for fen in (original, chess.Board(original).mirror().fen()):
                oracle, board = chess.Board(fen), Board(fen)
                self.assertTrue(oracle.is_valid(), fen)
                for captures_only in (False, True):
                    expected = {move.uci() for move in oracle.legal_moves
                                if not captures_only or oracle.is_capture(move) or move.promotion}
                    actual = list(generate_legal_moves(board, captures_only))
                    self.assertEqual({move.uci() for move in actual}, expected, fen)
                    self.assertEqual(actual, list(generate_legal_moves_reference(board, captures_only)))

    def test_castling_en_passant_promotion_and_capture_restore_on_error(self):
        fixtures = (
            ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1"),
            ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1c1"),
            ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6"),
            ("3r3k/2P5/8/8/8/8/8/K7 w - - 0 1", "c7d8n"),
            (EXTRA[0], "e1e2"),
        )
        for fen, uci in fixtures:
            board = Board(fen)
            move = next(move for move in generate_pseudo_legal_moves(board) if move.uci() == uci)
            before = copy.deepcopy(board.__dict__)
            with patch.object(Board, "is_square_attacked", side_effect=RuntimeError("probe failure")):
                with self.assertRaisesRegex(RuntimeError, "probe failure"):
                    _king_safe_after(board, move, board.side_to_move, board.king_squares[board.side_to_move])
            self.assertEqual(board.__dict__, before)

    def test_fast_generator_does_not_update_hashes_history_or_undo_stacks(self):
        for fen in EXTRA + SPECIAL:
            board = Board(fen)
            expected = list(generate_legal_moves_reference(board))
            before = copy.deepcopy(board.__dict__)
            with patch.object(Board, "make_move", side_effect=AssertionError("full move not allowed")), \
                 patch.object(Board, "unmake_move", side_effect=AssertionError("full undo not allowed")):
                self.assertEqual(list(generate_legal_moves(board)), expected)
            self.assertEqual(board.__dict__, before)

    def test_single_position_checks_along_deterministic_legal_playout(self):
        oracle = chess.Board()
        rng = random.Random(7)
        for _ in range(40):
            board = Board(oracle.fen())
            before = copy.deepcopy(board.__dict__)
            moves = list(generate_legal_moves(board))
            self.assertEqual({move.uci() for move in moves}, {move.uci() for move in oracle.legal_moves})
            self.assertEqual(moves, list(generate_legal_moves_reference(board)))
            self.assertEqual(board.__dict__, before)
            if not moves:
                break
            oracle.push_uci(rng.choice(moves).uci())


if __name__ == "__main__":
    unittest.main()
