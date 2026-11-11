"""Shared move-generation preparation must preserve legality, order and board state."""

import copy
import unittest
from unittest.mock import patch

from engine.board import Board
from engine import movegen
from engine.movegen import LegalMoveContext, generate_legal_moves, generate_legal_moves_reference
from tests.test_movegen_equivalence import SPECIAL
from tools.bench import POSITIONS


class MoveContextTests(unittest.TestCase):
    def test_shared_context_matches_reference_including_move_order(self):
        for fen in SPECIAL + tuple(fen for _, fen in POSITIONS):
            with self.subTest(fen=fen):
                board = Board(fen)
                before = copy.deepcopy(board.__dict__)
                context = LegalMoveContext(board)
                for captures_only in (False, True):
                    self.assertEqual(list(generate_legal_moves(board, captures_only, context=context)),
                                     list(generate_legal_moves_reference(board, captures_only)))
                self.assertEqual(board.__dict__, before)

    def test_probe_and_capture_pass_prepare_pins_and_pieces_once(self):
        board = Board(POSITIONS[1][1])
        with patch.object(movegen, "_pinned_squares", wraps=movegen._pinned_squares) as pins, \
             patch.object(movegen, "_ordered_pieces", wraps=movegen._ordered_pieces) as pieces:
            context = LegalMoveContext(board, known_in_check=False)
            self.assertIsNotNone(next(generate_legal_moves(board, context=context), None))
            captures = list(generate_legal_moves(board, captures_only=True, context=context))
            self.assertEqual(pins.call_count, 1)
            self.assertEqual(pieces.call_count, 1)
        self.assertEqual(captures, list(generate_legal_moves_reference(board, captures_only=True)))

    def test_changed_position_is_rejected_and_unmake_restores_validity(self):
        board = Board()
        before = copy.deepcopy(board.__dict__)
        context = LegalMoveContext(board)
        move = next(generate_legal_moves(board))
        board.make_move(move)
        try:
            with self.assertRaisesRegex(ValueError, "restored board"):
                list(generate_legal_moves(board, context=context))
        finally:
            board.unmake_move()
        self.assertEqual(list(generate_legal_moves(board, context=context)),
                         list(generate_legal_moves_reference(board)))
        self.assertEqual(board.__dict__, before)

    def test_null_move_requires_restoration_too(self):
        board = Board()
        context = LegalMoveContext(board)
        board.make_null_move()
        try:
            with self.assertRaises(ValueError):
                list(generate_legal_moves(board, context=context))
        finally:
            board.unmake_null_move()
        self.assertEqual(list(generate_legal_moves(board, context=context)),
                         list(generate_legal_moves_reference(board)))

    def test_context_is_bound_to_its_board_even_if_fen_matches(self):
        first, second = Board(), Board()
        with self.assertRaises(ValueError):
            list(generate_legal_moves(second, context=LegalMoveContext(first)))

    def test_check_status_cannot_conflict_with_context(self):
        board = Board()
        with self.assertRaisesRegex(ValueError, "conflicts"):
            list(generate_legal_moves(board, known_in_check=True, context=LegalMoveContext(board)))


if __name__ == "__main__":
    unittest.main()
