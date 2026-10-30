"""Polyglot keys and book lookup must match python-chess exactly."""

import random
import struct
import tempfile
import unittest
from pathlib import Path

import chess
import chess.polyglot

from engine.board import Board
from engine.book import PolyglotBook, polyglot_hash
from engine.uci import UciSession

FENS = (
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3",
    "4k3/P7/8/8/8/8/8/4K3 w - - 0 1",
)


def startpos_key() -> int:
    return chess.polyglot.zobrist_hash(chess.Board())


def encode(from_square: int, to_square: int, promotion: int = 0) -> int:
    """Polyglot move encoding for 0-based 8x8 squares (a1=0)."""
    from_file, from_rank = from_square & 7, from_square >> 3
    to_file, to_rank = to_square & 7, to_square >> 3
    return (promotion << 12) | (from_rank << 9) | (from_file << 6) | (to_rank << 3) | to_file


def write_book(path: Path, entries: list[tuple[int, int, int]]) -> None:
    with path.open("wb") as stream:
        for key, move, weight in sorted(entries):
            stream.write(struct.pack(">QHHI", key, move, weight, 0))
        stream.write(b"\0" * 16)


class HashTests(unittest.TestCase):
    def test_engine_matches_python_chess(self) -> None:
        for fen in FENS:
            with self.subTest(fen=fen):
                self.assertEqual(polyglot_hash(Board(fen)), chess.polyglot.zobrist_hash(chess.Board(fen)))


class BookLookupTests(unittest.TestCase):
    def test_finds_a_start_position_book_move(self) -> None:
        # e2e4: from e2 (12) to e4 (28) on the a1=0 board.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.bin"
            write_book(path, [(startpos_key(), encode(12, 28), 10)])
            book = PolyglotBook(path)
            move = book.find_move(Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"))
        self.assertIsNotNone(move)
        self.assertEqual(move.uci(), "e2e4")

    def test_zero_weight_entry_is_never_chosen_against_a_positive_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.bin"
            # e2e4 weight 1, d2d4 weight 0; the rng must always pick e2e4.
            write_book(path, [(startpos_key(), encode(12, 28), 1), (startpos_key(), encode(11, 27), 0)])
            book = PolyglotBook(path)
            board = Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
            moves = {book.find_move(board, random.Random(seed)).uci() for seed in range(20)}
        self.assertEqual(moves, {"e2e4"})

    def test_castling_is_decoded_as_a_king_move(self) -> None:
        fen = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
        key = chess.polyglot.zobrist_hash(chess.Board(fen))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.bin"
            # e1h1 encodes white kingside castling; e1=4, h1=7.
            write_book(path, [(key, encode(4, 7), 10)])
            book = PolyglotBook(path)
            move = book.find_move(Board(fen))
        self.assertIsNotNone(move)
        self.assertEqual(move.uci(), "e1g1")

    def test_promotion_is_decoded(self) -> None:
        fen = "4k3/P7/8/8/8/8/8/4K3 w - - 0 1"
        key = chess.polyglot.zobrist_hash(chess.Board(fen))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.bin"
            # a7a8q: a7=48, a8=56, queen promotion code 4.
            write_book(path, [(key, encode(48, 56, 4), 10)])
            book = PolyglotBook(path)
            move = book.find_move(Board(fen))
        self.assertIsNotNone(move)
        self.assertEqual(move.uci(), "a7a8q")

    def test_missing_key_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.bin"
            write_book(path, [(12345, encode(12, 28), 10)])
            book = PolyglotBook(path)
            self.assertIsNone(book.find_move(Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")))


class UciBookTests(unittest.TestCase):
    def make_book(self, directory: str) -> Path:
        path = Path(directory) / "book.bin"
        write_book(path, [(startpos_key(), encode(12, 28), 10)])
        return path

    def test_book_option_is_declared(self) -> None:
        text = "\n".join(UciSession().handle_line("uci"))
        self.assertIn("option name OwnBook type check default false", text)
        self.assertIn("option name BookFile type string", text)

    def test_enabled_book_answers_from_the_start_position(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session = UciSession()
            path = self.make_book(directory)
            self.assertEqual(session.handle_line(f"setoption name BookFile value {path}"), [])
            self.assertEqual(session.handle_line("setoption name OwnBook value true"), [])
            session.handle_line("position startpos")
            output = session.handle_line("go depth 1")
        self.assertTrue(any("book move" in line for line in output))
        self.assertIn("bestmove e2e4", output)

    def test_book_is_off_by_default(self) -> None:
        session = UciSession()
        session.handle_line("position startpos")
        output = session.handle_line("go depth 1")
        self.assertFalse(any("book move" in line for line in output))

    def test_missing_book_file_is_reported(self) -> None:
        session = UciSession()
        output = session.handle_line("setoption name BookFile value does-not-exist.bin")
        self.assertTrue(output and output[0].startswith("info string"))


if __name__ == "__main__":
    unittest.main()
