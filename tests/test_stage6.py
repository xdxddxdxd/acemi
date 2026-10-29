"""Stage 6 tests: null move on the board, forward pruning and ordering heuristics."""

import unittest

from engine.board import BLACK, WHITE, Board
from engine.movegen import generate_legal_moves
from engine.search import Searcher, _has_non_pawn_material, _SearchStopped, order_moves


class NullMoveBoardTests(unittest.TestCase):
    def test_null_move_round_trip_restores_state(self) -> None:
        board = Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
        fen, key, hashes = board.to_fen(), board.zobrist_hash, list(board.position_hashes)
        board.make_null_move()
        self.assertEqual(board.side_to_move, BLACK)
        board.unmake_null_move()
        self.assertEqual(board.to_fen(), fen)
        self.assertEqual(board.zobrist_hash, key)
        self.assertEqual(board.position_hashes, hashes)

    def test_null_move_hash_matches_recomputation(self) -> None:
        for fen in (
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            # Black can capture en passant on e3, so the hash contains an e-file term.
            "rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
        ):
            board = Board(fen)
            board.make_null_move()
            self.assertEqual(board.zobrist_hash, board.compute_zobrist_hash())
            self.assertIsNone(board.en_passant_square)
            board.unmake_null_move()
            self.assertEqual(board.zobrist_hash, board.compute_zobrist_hash())

    def test_moves_work_after_null_move(self) -> None:
        board = Board()
        board.make_null_move()
        moves = list(generate_legal_moves(board))
        self.assertEqual(len(moves), 20)
        board.make_move(moves[0])
        board.unmake_move()
        board.unmake_null_move()
        self.assertEqual(board.side_to_move, WHITE)


class HeuristicTests(unittest.TestCase):
    def test_non_pawn_material_guard(self) -> None:
        board = Board("8/8/8/4k3/8/4K3/4P3/8 w - - 0 1")
        self.assertFalse(_has_non_pawn_material(board, WHITE))
        self.assertTrue(_has_non_pawn_material(Board(), WHITE))

    def test_killer_move_is_ordered_before_other_quiet_moves(self) -> None:
        board = Board()
        moves = list(generate_legal_moves(board))
        killer = next(m for m in moves if m.uci() == "a2a3")
        order_moves(board, moves, None, (killer,), None)
        self.assertEqual(moves[0], killer)

    def test_history_raises_a_quiet_move(self) -> None:
        board = Board()
        moves = list(generate_legal_moves(board))
        target = next(m for m in moves if m.uci() == "h2h3")
        history = {(board.squares[target.from_square], target.to_square): 50}
        order_moves(board, moves, None, (), history)
        self.assertEqual(moves[0], target)

    def test_all_heuristics_find_mate_in_one(self) -> None:
        board = Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
        result = Searcher().search(board, depth=3)
        assert result.best_move is not None
        self.assertEqual(result.best_move.uci(), "h5f7")
        self.assertEqual(result.mate, 1)

    def test_search_leaves_board_unchanged(self) -> None:
        board = Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
        fen, key, hashes = board.to_fen(), board.zobrist_hash, list(board.position_hashes)
        result = Searcher().search(board, depth=4)
        self.assertEqual(board.to_fen(), fen)
        self.assertEqual(board.zobrist_hash, key)
        self.assertEqual(board.position_hashes, hashes)
        self.assertEqual(board.null_stack, [])
        legal = {m.uci() for m in generate_legal_moves(board)}
        assert result.best_move is not None
        self.assertIn(result.best_move.uci(), legal)

    def test_heuristics_can_be_disabled(self) -> None:
        board = Board()
        plain = Searcher(null_move=False, lmr=False, killers=False).search(board, depth=3)
        full = Searcher().search(board, depth=3)
        legal = {m.uci() for m in generate_legal_moves(board)}
        for result in (plain, full):
            assert result.best_move is not None
            self.assertIn(result.best_move.uci(), legal)
            self.assertEqual(result.depth, 3)

    def test_kings_and_pawns_zugzwang_is_not_pruned_away(self) -> None:
        # Kings and pawns only: the null-move guard must skip pruning here
        # (zugzwang is common). The search just has to finish and stay legal.
        board = Board("8/8/k1K5/8/1P6/8/8/8 w - - 0 1")
        result = Searcher().search(board, depth=5)
        assert result.best_move is not None
        self.assertIn(result.best_move.uci(), {m.uci() for m in generate_legal_moves(board)})


class _InterruptedSecondIteration(Searcher):
    """Finishes depth 1, then is interrupted during depth 2 (optionally with a partial result)."""

    def __init__(self, partial_index: int | None) -> None:
        super().__init__()
        self.partial_index = partial_index
        self.moves_seen: list = []

    def _search_root(self, board, moves, depth, rng):  # type: ignore[no-untyped-def]
        if depth == 1:
            self.moves_seen = list(moves)
            return moves[0], 10
        self._partial = None if self.partial_index is None else (moves[self.partial_index], 50)
        raise _SearchStopped


class PartialIterationTests(unittest.TestCase):
    def test_interrupted_iteration_uses_its_best_move_so_far(self) -> None:
        searcher = _InterruptedSecondIteration(partial_index=1)
        result = searcher.search(Board(), depth=3)
        self.assertEqual(result.best_move, searcher.moves_seen[1])
        self.assertEqual(result.score, 50)
        self.assertEqual(result.depth, 1)  # Only depth 1 completed.

    def test_interrupted_before_any_root_move_keeps_previous_result(self) -> None:
        searcher = _InterruptedSecondIteration(partial_index=None)
        result = searcher.search(Board(), depth=3)
        self.assertEqual(result.best_move, searcher.moves_seen[0])
        self.assertEqual(result.score, 10)
        self.assertEqual(result.depth, 1)


if __name__ == "__main__":
    unittest.main()
