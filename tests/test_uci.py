"""UCI session tests (in-process; no subprocess or external engine needed)."""

import unittest

from engine.board import STARTING_FEN, Board
from engine.movegen import generate_legal_moves
from engine.uci import UciSession


def _bestmove_line(lines: list[str]) -> str:
    for line in reversed(lines):
        if line.startswith("bestmove "):
            return line
    raise AssertionError(f"no bestmove in {lines!r}")


class UciSessionTests(unittest.TestCase):
    def test_uci_handshake(self) -> None:
        lines = UciSession().handle_line("uci")
        self.assertEqual(lines[-1], "uciok")
        self.assertTrue(any(line.startswith("id name Acemi") for line in lines))
        self.assertTrue(any("name Seed" in line for line in lines))

    def test_isready(self) -> None:
        self.assertEqual(UciSession().handle_line("isready"), ["readyok"])

    def test_go_returns_a_legal_move(self) -> None:
        session = UciSession()
        session.handle_line("position startpos")
        output = session.handle_line("go depth 2")
        best = _bestmove_line(output)
        legal = {move.uci() for move in generate_legal_moves(Board(STARTING_FEN))}
        self.assertIn(best.split()[1], legal)
        self.assertTrue(any(line.startswith("info depth") for line in output))

    def test_position_with_moves_is_applied(self) -> None:
        session = UciSession()
        self.assertEqual(session.handle_line("position startpos moves e2e4 e7e5"), [])
        self.assertEqual(
            session.board.to_fen(),
            "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2",
        )

    def test_position_fen_with_moves(self) -> None:
        session = UciSession()
        fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
        self.assertEqual(session.handle_line(f"position fen {fen} moves e2e4"), [])
        self.assertEqual(session.board.to_fen(), "4k3/8/8/8/4P3/8/8/4K3 b - e3 0 1")

    def test_illegal_move_is_reported_and_position_unchanged(self) -> None:
        session = UciSession()
        output = session.handle_line("position startpos moves e2e5")
        self.assertEqual(len(output), 1)
        self.assertTrue(output[0].startswith("info string"))
        self.assertEqual(session.board.to_fen(), STARTING_FEN)

    def test_no_legal_moves_gives_null_move(self) -> None:
        session = UciSession()
        session.handle_line("position fen 7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        output = session.handle_line("go depth 1")
        self.assertEqual(_bestmove_line(output), "bestmove 0000")

    def test_search_is_deterministic(self) -> None:
        first, second = UciSession(), UciSession()
        for session in (first, second):
            session.handle_line("position startpos moves e2e4")
        self.assertEqual(
            _bestmove_line(first.handle_line("go depth 2")),
            _bestmove_line(second.handle_line("go depth 2")),
        )

    def test_setoption_updates_seed(self) -> None:
        session = UciSession()
        self.assertEqual(session.handle_line("setoption name Seed value 7"), [])
        self.assertEqual(session.seed, 7)

    def test_go_infinite_waits_for_stop(self) -> None:
        session = UciSession()
        session.handle_line("position startpos")
        self.assertEqual(session.handle_line("go infinite"), [])
        self.assertIsNotNone(session._infinite_thread)
        output = session.handle_line("stop")
        best = _bestmove_line(output)
        self.assertTrue(best.startswith("bestmove "))
        self.assertIsNone(session._infinite_thread)

    def test_go_nodes_limit(self) -> None:
        session = UciSession()
        session.handle_line("position startpos")
        output = session.handle_line("go nodes 32")
        info = next(line for line in output if line.startswith("info depth"))
        self.assertIn(" nodes 32 ", info)
        self.assertTrue(any(line.startswith("bestmove ") for line in output))

    def test_quit_sets_flag(self) -> None:
        session = UciSession()
        session.handle_line("quit")
        self.assertTrue(session.quit_requested)


if __name__ == "__main__":
    unittest.main()
