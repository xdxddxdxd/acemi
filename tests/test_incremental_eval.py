import unittest

from engine.board import Board, STARTING_FEN
from engine.eval.classic import (
    MAX_PHASE,
    PHASE_WEIGHT,
    _EG_VALUES,
    _MG_VALUES,
    evaluate_classic,
)
from engine.movegen import find_legal_move
from tests.test_perft import KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6


def full_totals(board: Board) -> tuple[int, int, int]:
    mg = 0
    eg = 0
    phase = 0
    for piece, squares in board.piece_squares.items():
        sign = 1 if piece > 0 else -1
        for square in squares:
            mg += sign * _MG_VALUES[piece][square]
            eg += sign * _EG_VALUES[piece][square]
        phase += PHASE_WEIGHT[abs(piece)] * len(squares)
    return mg, eg, phase


def incremental_totals(board: Board) -> tuple[int, int, int]:
    return (
        getattr(board, "classic_mg", None),
        getattr(board, "classic_eg", None),
        getattr(board, "classic_phase", None),
    )


class IncrementalEvalTests(unittest.TestCase):
    def assert_matches_full(self, board: Board) -> None:
        self.assertEqual(incremental_totals(board), full_totals(board))

    def test_fen_initializes_totals(self) -> None:
        for fen in (STARTING_FEN, KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6):
            with self.subTest(fen=fen):
                self.assert_matches_full(Board(fen))

    def test_capture_and_unmake_restore_totals(self) -> None:
        board = Board(KIWIPETE)
        before = full_totals(board)
        board.make_move(find_legal_move(board, "e2a6"))
        self.assert_matches_full(board)
        board.unmake_move()
        self.assertEqual(incremental_totals(board), before)

    def test_castling_updates_king_and_rook(self) -> None:
        board = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        before = full_totals(board)
        board.make_move(find_legal_move(board, "e1g1"))
        self.assert_matches_full(board)
        board.unmake_move()
        self.assertEqual(incremental_totals(board), before)

    def test_en_passant_removes_captured_pawn(self) -> None:
        board = Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2")
        before = full_totals(board)
        board.make_move(find_legal_move(board, "e5d6"))
        self.assert_matches_full(board)
        board.unmake_move()
        self.assertEqual(incremental_totals(board), before)

    def test_capture_promotion_replaces_both_piece_values(self) -> None:
        board = Board("1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        before = full_totals(board)
        board.make_move(find_legal_move(board, "a7b8q"))
        self.assert_matches_full(board)
        board.unmake_move()
        self.assertEqual(incremental_totals(board), before)

    def test_null_move_preserves_piece_totals(self) -> None:
        board = Board()
        before = full_totals(board)
        board.make_null_move()
        self.assert_matches_full(board)
        self.assertEqual(incremental_totals(board), before)
        board.unmake_null_move()
        self.assertEqual(incremental_totals(board), before)

    def test_evaluate_classic_reads_incremental_totals(self) -> None:
        board = Board()
        before = evaluate_classic(board)
        board.classic_mg = getattr(board, "classic_mg", 0) + MAX_PHASE
        self.assertEqual(evaluate_classic(board), before + MAX_PHASE)


if __name__ == "__main__":
    unittest.main()
