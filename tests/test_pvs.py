"""Principal variation search: same value as plain alpha-beta, and it enables null-move pruning."""

import unittest
from unittest.mock import patch

from engine.board import Board
from engine.movegen import generate_legal_moves
from engine.search import Searcher
from engine.uci import UciSession

POSITIONS = (
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",  # Kiwipete
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
    "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",  # back-rank mate in one
)


class PvsEquivalenceTests(unittest.TestCase):
    """Without null move and LMR (which are approximations) PVS must give the exact
    same value as alpha-beta: it only changes how much work is needed to prove it."""

    def test_same_score_as_alpha_beta(self) -> None:
        for fen in POSITIONS:
            for depth in (2, 3) if fen in POSITIONS[2:3] else (2, 3, 4):
                with self.subTest(fen=fen, depth=depth):
                    plain = Searcher(pvs=False, null_move=False, lmr=False).search(Board(fen), depth=depth)
                    pvs = Searcher(pvs=True, null_move=False, lmr=False).search(Board(fen), depth=depth)
                    self.assertEqual(pvs.score, plain.score)
                    self.assertEqual(pvs.depth, plain.depth)

    def test_same_score_with_killers_off(self) -> None:
        fen = POSITIONS[2]
        plain = Searcher(pvs=False, null_move=False, lmr=False, killers=False).search(Board(fen), depth=3)
        pvs = Searcher(pvs=True, null_move=False, lmr=False, killers=False).search(Board(fen), depth=3)
        self.assertEqual(pvs.score, plain.score)

    def test_best_move_is_legal_and_mate_is_found(self) -> None:
        board = Board(POSITIONS[6])
        result = Searcher(pvs=True).search(board, depth=3)
        assert result.best_move is not None
        self.assertIn(result.best_move.uci(), {m.uci() for m in generate_legal_moves(board)})
        self.assertEqual(result.best_move.uci(), "a1a8")
        self.assertEqual(result.mate, 1)

    def test_runs_with_every_feature_on(self) -> None:
        for fen in POSITIONS:
            with self.subTest(fen=fen):
                board = Board(fen)
                result = Searcher(pvs=True, null_move=True, lmr=True, killers=True).search(board, depth=4)
                assert result.best_move is not None
                self.assertIn(result.best_move.uci(), {m.uci() for m in generate_legal_moves(board)})

    def test_board_is_restored_after_search(self) -> None:
        board = Board(POSITIONS[2])
        before = (board.to_fen(), board.zobrist_hash)
        Searcher(pvs=True).search(board, depth=4)
        self.assertEqual((board.to_fen(), board.zobrist_hash), before)


class PvsEnablesNullMoveTests(unittest.TestCase):
    def _null_calls(self, fen: str, pvs: bool) -> int:
        calls = [0]
        original = Board.make_null_move

        def counting(board: Board):
            calls[0] += 1
            return original(board)

        with patch.object(Board, "make_null_move", counting):
            Searcher(pvs=pvs, null_move=True, lmr=False).search(Board(fen), depth=5)
        return calls[0]

    def test_null_move_never_runs_with_null_move_off(self) -> None:
        calls = [0]
        original = Board.make_null_move

        def counting(board: Board):
            calls[0] += 1
            return original(board)

        with patch.object(Board, "make_null_move", counting):
            Searcher(pvs=True, null_move=False).search(Board(POSITIONS[1]), depth=5)
        self.assertEqual(calls[0], 0)

    def test_pvs_makes_null_move_run(self) -> None:
        fen = POSITIONS[1]
        self.assertEqual(self._null_calls(fen, pvs=False), 0)
        self.assertGreater(self._null_calls(fen, pvs=True), 0)

    def test_null_move_is_skipped_without_non_pawn_material(self) -> None:
        # King and pawns only: zugzwang is possible, so null move must not be tried.
        fen = "8/8/p1p5/1p1p4/1P1P4/P1P5/8/k1K5 w - - 0 1"
        self.assertEqual(self._null_calls(fen, pvs=True), 0)


class PvsOptionTests(unittest.TestCase):
    def test_off_by_default(self) -> None:
        self.assertFalse(Searcher().use_pvs)
        self.assertFalse(UciSession().searcher.use_pvs)

    def test_uci_option(self) -> None:
        session = UciSession()
        self.assertIn("option name PVS type check default false", "\n".join(session.handle_line("uci")))
        session.handle_line("setoption name PVS value true")
        self.assertTrue(session.searcher.use_pvs)
        session.handle_line("setoption name PVS value false")
        self.assertFalse(session.searcher.use_pvs)


if __name__ == "__main__":
    unittest.main()
