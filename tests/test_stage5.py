"""Stage 5 tests: move ordering, transposition table, persistent searcher."""

import random
import unittest

from engine.board import Board
from engine.eval.classic import pst_delta
from engine.movegen import generate_legal_moves
from engine.search import (
    MATE_SCORE,
    Searcher,
    from_tt_score,
    order_moves,
    search,
    to_tt_score,
)
from engine.uci import UciSession


class OrderingTests(unittest.TestCase):
    def test_captures_come_first_and_best_victim_leads(self) -> None:
        # White rook a1 can take the queen on a5 or the pawn on h1... use a simple setup:
        # white pawn e4 attacks d5 (queen) and f5 (pawn).
        board = Board("4k3/8/8/3q1p2/4P3/8/8/4K3 w - - 0 1")
        moves = list(generate_legal_moves(board))
        order_moves(board, moves)
        self.assertEqual(moves[0].uci(), "e4d5")
        self.assertEqual(moves[1].uci(), "e4f5")

    def test_lower_attacker_is_preferred_for_same_victim(self) -> None:
        # Pawn b4 and queen d4 can both take the knight on c5.
        board = Board("4k3/8/8/2n5/1P1Q4/8/8/4K3 w - - 0 1")
        moves = list(generate_legal_moves(board))
        order_moves(board, moves)
        self.assertEqual(moves[0].uci(), "b4c5")

    def test_hash_move_goes_first(self) -> None:
        board = Board()
        moves = list(generate_legal_moves(board))
        wanted = next(m for m in moves if m.uci() == "a2a3")
        order_moves(board, moves, wanted)
        self.assertEqual(moves[0], wanted)
        self.assertEqual(len(moves), 20)

    def test_ordering_keeps_all_moves(self) -> None:
        board = Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
        before = sorted(m.uci() for m in generate_legal_moves(board))
        moves = list(generate_legal_moves(board))
        order_moves(board, moves)
        self.assertEqual(before, sorted(m.uci() for m in moves))

    def test_pst_delta_is_signed_difference(self) -> None:
        board = Board()
        knight = board.squares[0x76]  # g1 knight is white (positive)
        self.assertGreater(knight, 0)
        # g1 -> f3 is a development gain in the table.
        self.assertGreater(pst_delta(knight, 0x76, 0x55), 0)


class TtScoreTests(unittest.TestCase):
    def test_mate_score_round_trip(self) -> None:
        for score in (MATE_SCORE - 5, -(MATE_SCORE - 5), 123, -45):
            self.assertEqual(from_tt_score(to_tt_score(score, 3), 3), score)

    def test_mate_is_stored_relative_to_node(self) -> None:
        # Mate in 2 plies from a node at ply 4 is mate in 6 from the root.
        node_score = MATE_SCORE - 2
        stored = to_tt_score(node_score, 4)
        self.assertEqual(from_tt_score(stored, 6), MATE_SCORE - 8)


class SearcherTests(unittest.TestCase):
    def test_table_fills_and_clears(self) -> None:
        searcher = Searcher(hash_mb=1)
        searcher.search(Board(), depth=3)
        self.assertGreater(searcher.tt_size, 0)
        searcher.clear_tt()
        self.assertEqual(searcher.tt_size, 0)

    def test_zero_hash_disables_table(self) -> None:
        searcher = Searcher(hash_mb=0)
        result = searcher.search(Board(), depth=2)
        self.assertEqual(searcher.tt_size, 0)
        self.assertIsNotNone(result.best_move)

    def test_table_never_exceeds_capacity(self) -> None:
        searcher = Searcher(hash_mb=1)
        searcher.search(Board(), depth=3)
        self.assertLessEqual(searcher.tt_size, searcher.tt_capacity)

    def test_finds_mate_in_one_with_table(self) -> None:
        board = Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        result = Searcher().search(board, depth=3)
        assert result.best_move is not None
        self.assertEqual(result.best_move.uci(), "a1a8")
        self.assertEqual(result.mate, 1)

    def test_reused_table_still_returns_legal_move(self) -> None:
        searcher = Searcher()
        board = Board()
        first = searcher.search(board, depth=3, rng=random.Random(1))
        second = searcher.search(board, depth=3, rng=random.Random(1))
        legal = {m.uci() for m in generate_legal_moves(Board())}
        assert first.best_move is not None and second.best_move is not None
        self.assertIn(first.best_move.uci(), legal)
        self.assertIn(second.best_move.uci(), legal)

    def test_ordering_reduces_nodes_versus_no_table_is_not_required(self) -> None:
        # Sanity only: a depth-3 search of the start position completes quickly.
        result = search(Board(), depth=3)
        self.assertEqual(result.depth, 3)
        self.assertGreater(result.nodes, 0)

    def test_interrupted_first_iteration_returns_legal_move(self) -> None:
        board = Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
        result = search(board, depth=4, nodes_limit=50)
        legal = {m.uci() for m in generate_legal_moves(board)}
        assert result.best_move is not None
        self.assertIn(result.best_move.uci(), legal)
        self.assertEqual(result.depth, 0)

    def test_fallback_prefers_free_capture(self) -> None:
        # Undefended queen on d5 can be taken by the e4 pawn; with almost no
        # search budget the ordered fallback should still pick it.
        board = Board("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1")
        result = search(board, depth=4, nodes_limit=1)
        assert result.best_move is not None
        self.assertEqual(result.best_move.uci(), "e4d5")


class UciIntegrationTests(unittest.TestCase):
    def test_hash_option_resizes_table(self) -> None:
        session = UciSession()
        session.handle_line("setoption name Hash value 2")
        self.assertEqual(session.searcher.tt_capacity, 2 * 5000)

    def test_ucinewgame_clears_table(self) -> None:
        session = UciSession()
        session.handle_line("position startpos")
        session.handle_line("go depth 2")
        self.assertGreater(session.searcher.tt_size, 0)
        session.handle_line("ucinewgame")
        self.assertEqual(session.searcher.tt_size, 0)


if __name__ == "__main__":
    unittest.main()
