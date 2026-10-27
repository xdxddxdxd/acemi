"""Reference perft positions from the Acemi project plan."""

import unittest

from engine.board import Board, STARTING_FEN
from engine.movegen import perft, perft_divide, perft_stats

KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq -"
POSITION_3 = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - -"
POSITION_4 = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
POSITION_5 = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"
POSITION_6 = "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10"

REFERENCES = (
    ("Starting position", STARTING_FEN, (20, 400, 8902, 197281, 4865609, 119060324)),
    ("Kiwipete", KIWIPETE, (48, 2039, 97862, 4085603)),
    ("Position 3", POSITION_3, (14, 191, 2812, 43238, 674624)),
    ("Position 4", POSITION_4, (6, 264, 9467, 422333)),
    ("Position 5", POSITION_5, (44, 1486, 62379, 2103487)),
    ("Position 6", POSITION_6, (46, 2079, 89890, 3894594)),
)


class PerftReferenceTests(unittest.TestCase):
    def test_all_plan_reference_counts(self) -> None:
        for name, fen, expected_counts in REFERENCES:
            for depth, expected in enumerate(expected_counts, start=1):
                with self.subTest(position=name, depth=depth):
                    board = Board(fen)
                    actual = perft(board, depth)
                    print(f"{name} depth {depth}: {actual}")
                    if actual != expected:
                        divide = perft_divide(board, depth)
                        self.fail(
                            f"{name} depth {depth}: expected {expected}, got {actual}; "
                            f"root split: {divide}"
                        )
                    self.assertEqual(board.to_fen(), Board(fen).to_fen(), "perft changed the position")
                    self.assertEqual(board.zobrist_hash, board.compute_zobrist_hash())

    def test_perft_stats_sum_to_leaf_count(self) -> None:
        for name, fen, counts in REFERENCES:
            board = Board(fen)
            stats = perft_stats(board, 1)
            self.assertEqual(stats["nodes"], counts[0], name)
            self.assertGreaterEqual(stats["captures"], 0)
            self.assertGreaterEqual(stats["checks"], 0)


if __name__ == "__main__":
    unittest.main()
