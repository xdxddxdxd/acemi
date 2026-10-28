"""Stage 4 tests: piece-square eval, capture generation, quiescence, time control."""

import unittest

from engine.board import STARTING_FEN, Board
from engine.eval.base import evaluate
from engine.movegen import generate_legal_moves
from engine.search import search
from engine.uci import UciSession, time_budget_ms
from tests.test_perft import KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6

REFERENCE_FENS = (STARTING_FEN, KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6)


class PieceSquareEvalTests(unittest.TestCase):
    def test_start_position_is_exactly_zero(self) -> None:
        self.assertEqual(evaluate(Board()), 0)

    def test_central_knight_beats_corner_knight(self) -> None:
        centre = evaluate(Board("4k3/8/8/8/4N3/8/8/4K3 w - - 0 1"))
        corner = evaluate(Board("4k3/8/8/8/8/8/8/N3K3 w - - 0 1"))
        self.assertGreater(centre, corner)

    def test_endgame_king_prefers_the_centre(self) -> None:
        centre = evaluate(Board("4k3/8/8/8/4K3/8/8/8 w - - 0 1"))
        home = evaluate(Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1"))
        self.assertGreater(centre, home)

    def test_cornered_enemy_king_is_better_for_us(self) -> None:
        # Same material, only the defending king differs: edge is worse for it.
        edge = evaluate(Board("k7/8/8/8/8/8/8/R3K3 w - - 0 1"))
        centre = evaluate(Board("8/8/8/3k4/8/8/8/R3K3 w - - 0 1"))
        self.assertGreater(edge, centre)

    def test_score_flips_sign_with_the_side_to_move(self) -> None:
        for fen in REFERENCE_FENS:
            white = Board(fen)
            fields = fen.split()
            fields[1] = "b"
            fields[3] = "-"  # Avoid an en-passant square on the wrong rank.
            black = Board(" ".join(fields))
            self.assertEqual(evaluate(white), -evaluate(black), fen)


class CaptureGenerationTests(unittest.TestCase):
    def test_start_position_has_no_captures(self) -> None:
        self.assertEqual(list(generate_legal_moves(Board(), captures_only=True)), [])

    def test_kiwipete_has_eight_captures(self) -> None:
        # Reference perft statistics: 8 captures among the 48 legal moves.
        self.assertEqual(len(list(generate_legal_moves(Board(KIWIPETE), captures_only=True))), 8)

    def test_captures_are_a_subset_of_all_legal_moves(self) -> None:
        for fen in REFERENCE_FENS:
            board = Board(fen)
            everything = {move.uci() for move in generate_legal_moves(board)}
            captures = {move.uci() for move in generate_legal_moves(board, captures_only=True)}
            self.assertTrue(captures.issubset(everything), fen)

    def test_captures_only_never_makes_quiet_moves(self) -> None:
        for fen in REFERENCE_FENS:
            board = Board(fen)
            for move in generate_legal_moves(board, captures_only=True):
                target_piece = board.squares[move.to_square]
                is_en_passant = move.to_square == board.en_passant_square
                self.assertTrue(
                    target_piece != 0 or is_en_passant or move.promotion is not None,
                    f"{fen}: {move.uci()}",
                )

    def test_queen_promotion_push_is_generated(self) -> None:
        board = Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        moves = {move.uci() for move in generate_legal_moves(board, captures_only=True)}
        self.assertEqual(moves, {"a7a8q"})

    def test_movegen_leaves_the_board_unchanged(self) -> None:
        for fen in REFERENCE_FENS:
            board = Board(fen)
            before = (board.to_fen(), board.zobrist_hash)
            list(generate_legal_moves(board))
            list(generate_legal_moves(board, captures_only=True))
            self.assertEqual((board.to_fen(), board.zobrist_hash), before, fen)


class QuiescenceTests(unittest.TestCase):
    def test_does_not_grab_a_defended_pawn_with_the_queen(self) -> None:
        # Qxd6 wins a pawn on paper, but exd6 takes the queen.
        board = Board("4k3/4p3/3p4/8/8/8/8/3QK3 w - - 0 1")
        result = search(board, depth=1)
        assert result.best_move is not None
        self.assertNotEqual(result.best_move.uci(), "d1d6")

    def test_still_takes_an_undefended_piece(self) -> None:
        board = Board("4k3/8/3p4/8/8/8/8/3QK3 w - - 0 1")
        result = search(board, depth=1)
        assert result.best_move is not None
        self.assertEqual(result.best_move.uci(), "d1d6")


class TimeManagementTests(unittest.TestCase):
    def test_budget_is_a_share_of_the_clock(self) -> None:
        self.assertEqual(time_budget_ms(60_000), 60_000 // 30 - 30)

    def test_budget_uses_most_of_the_increment(self) -> None:
        self.assertEqual(time_budget_ms(30_000, 2_000), 30_000 // 30 + 1_500 - 30)

    def test_budget_never_exceeds_half_the_clock(self) -> None:
        self.assertEqual(time_budget_ms(1_000, 5_000), 500 - 30)

    def test_budget_is_at_least_one_millisecond(self) -> None:
        self.assertEqual(time_budget_ms(20), 1)

    def test_moves_to_go_changes_the_share(self) -> None:
        self.assertEqual(time_budget_ms(10_000, 0, 10), 1_000 - 30)

    def test_go_with_clock_returns_a_legal_move(self) -> None:
        session = UciSession()
        session.handle_line("position startpos")
        output = session.handle_line("go wtime 1500 btime 1500 winc 0 binc 0")
        best = [line for line in output if line.startswith("bestmove ")][0].split()[1]
        legal = {move.uci() for move in generate_legal_moves(Board())}
        self.assertIn(best, legal)

    def test_go_depth_overrides_the_default(self) -> None:
        session = UciSession()
        session.handle_line("position startpos")
        output = session.handle_line("go depth 1")
        info = [line for line in output if line.startswith("info depth")][0]
        self.assertTrue(info.startswith("info depth 1 "))


if __name__ == "__main__":
    unittest.main()
