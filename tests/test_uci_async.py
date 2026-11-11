"""UCI worker lifecycle and real pipe regressions; no match or Stockfish needed."""

from __future__ import annotations

import queue
import subprocess
import sys
import time
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from engine.board import Board, Move, parse_square
from engine.movegen import generate_legal_moves
from engine.search import SearchResult
from engine.uci import UciSession

ROOT = Path(__file__).resolve().parents[1]


def result() -> SearchResult:
    return SearchResult(Move(parse_square("e2"), parse_square("e4")), None, 0, 0, 0, None)


class AsyncSessionTests(unittest.TestCase):
    def setUp(self):
        self.output = queue.Queue()
        self.session = UciSession(on_output=self.output.put)
        self.addCleanup(self.session.close)

    def block_until_stopped(self):
        entered = Event()
        stopped = Event()
        calls = []

        def search(board, **kwargs):
            calls.append(kwargs)
            entered.set()
            if not kwargs["stop_event"].wait(5):
                raise AssertionError("Worker did not receive stop")
            stopped.set()
            return result()

        patcher = patch.object(self.session.searcher, "search", side_effect=search)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.session.close)
        return entered, stopped, calls

    def all_output(self, immediate=()):
        lines = list(immediate)
        while not self.output.empty():
            lines.extend(self.output.get_nowait())
        return lines

    def test_timed_search_is_ready_and_stops_once(self):
        entered, stopped, calls = self.block_until_stopped()
        self.assertEqual(self.session.handle_line("go movetime 60000"), [])
        self.assertTrue(entered.wait(5))
        self.assertEqual(self.session.handle_line("isready"), ["readyok"])
        self.assertFalse(stopped.is_set())
        lines = self.all_output(self.session.handle_line("stop"))
        self.assertTrue(stopped.is_set())
        self.assertEqual(calls[0]["movetime_ms"], 60000)
        self.assertEqual([line for line in lines if line.startswith("bestmove")], ["bestmove e2e4"])
        self.assertEqual(self.session.handle_line("stop"), [])
        self.assertFalse(self.session.searching)
        self.assertTrue(self.output.empty())

    def test_finite_search_publishes_without_another_input_command(self):
        entered, release = Event(), Event()

        def search(board, **kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Test did not release the worker")
            return result()

        with patch.object(self.session.searcher, "search", side_effect=search):
            self.addCleanup(release.set)
            self.assertEqual(self.session.handle_line("go depth 1"), [])
            self.assertTrue(entered.wait(5))
            release.set()
            lines = self.output.get(timeout=5)
            self.assertEqual(lines[-1], "bestmove e2e4")
            self.assertEqual(self.session.handle_line("stop"), [])
        self.assertTrue(self.output.empty())

    def test_infinite_search_does_not_publish_before_stop_even_if_finished(self):
        with patch.object(self.session.searcher, "search", return_value=result()):
            self.assertEqual(self.session.handle_line("go infinite"), [])
            lines = self.session.handle_line("stop")
        self.assertEqual(lines[-1], "bestmove e2e4")
        self.assertTrue(self.output.empty())
        self.assertEqual(self.session.handle_line("stop"), [])

    def test_position_waits_for_cancel_and_suppresses_old_result(self):
        entered, stopped, _ = self.block_until_stopped()
        self.session.handle_line("go depth 64")
        self.assertTrue(entered.wait(5))
        self.assertEqual(self.session.handle_line("position startpos moves e2e4"), [])
        self.assertTrue(stopped.is_set())
        self.assertFalse(self.session.searching)
        self.assertEqual(self.session.board.side_to_move, -1)
        self.assertTrue(self.output.empty())

    def test_option_change_waits_for_cancel_before_resizing(self):
        entered, stopped, _ = self.block_until_stopped()
        self.session.handle_line("go depth 64")
        self.assertTrue(entered.wait(5))
        self.assertEqual(self.session.handle_line("setoption name Hash value 2"), [])
        self.assertTrue(stopped.is_set())
        self.assertEqual(self.session.searcher.tt_capacity, 10000)
        self.assertTrue(self.output.empty())

    def test_eval_option_is_applied_only_after_the_old_worker_stops(self):
        entered = Event()
        observed = []

        def search(board, **kwargs):
            entered.set()
            if not kwargs["stop_event"].wait(5):
                raise AssertionError("Old worker did not stop")
            observed.append(self.session.eval_flags.passed_pawns)
            return result()

        with patch.object(self.session.searcher, "search", side_effect=search):
            self.session.handle_line("go depth 64")
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.session.handle_line("setoption name EvalPassedPawns value true"), [])
        self.assertEqual(observed, [False])
        self.assertTrue(self.session.eval_flags.passed_pawns)
        self.assertFalse(self.session.searching)
        self.assertTrue(self.output.empty())

    def test_new_game_cancels_before_replacing_the_board(self):
        entered, stopped, _ = self.block_until_stopped()
        self.session.handle_line("go depth 64")
        self.assertTrue(entered.wait(5))
        self.assertEqual(self.session.handle_line("ucinewgame"), [])
        self.assertTrue(stopped.is_set())
        self.assertEqual(self.session.board.to_fen(), Board().to_fen())
        self.assertTrue(self.output.empty())

    def test_quit_cancels_and_does_not_publish_an_old_move(self):
        entered, stopped, _ = self.block_until_stopped()
        self.session.handle_line("go depth 64")
        self.assertTrue(entered.wait(5))
        self.assertEqual(self.session.handle_line("quit"), [])
        self.assertTrue(stopped.is_set())
        self.assertTrue(self.session.quit_requested)
        self.assertFalse(self.session.searching)
        self.assertTrue(self.output.empty())

    def test_replacement_go_does_not_publish_the_cancelled_search(self):
        entered, stopped = Event(), Event()
        calls = []

        def search(board, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                entered.set()
                if not kwargs["stop_event"].wait(5):
                    raise AssertionError("Previous search was not cancelled")
                stopped.set()
            return result()

        with patch.object(self.session.searcher, "search", side_effect=search):
            self.session.handle_line("go depth 64")
            self.assertTrue(entered.wait(5))
            self.session.handle_line("go depth 1")
            lines = self.output.get(timeout=5)
            self.assertEqual(self.session.handle_line("stop"), [])
        self.assertTrue(stopped.is_set())
        self.assertEqual(len(calls), 2)
        self.assertEqual(lines[-1], "bestmove e2e4")
        self.assertTrue(self.output.empty())

    def test_worker_error_is_reported_once_instead_of_silently_hanging(self):
        with patch.object(self.session.searcher, "search", side_effect=ValueError("worker failure")):
            self.session.handle_line("go depth 1")
            lines = self.output.get(timeout=5)
            self.assertIn("Search failed: ValueError: worker failure", lines[0])
            self.assertEqual(lines[-1], "bestmove 0000")
            self.assertEqual(self.session.handle_line("stop"), [])
        self.assertTrue(self.output.empty())


class UciPipeTests(unittest.TestCase):
    """Exercise the actual CLI input loop, which a direct session test cannot."""

    def setUp(self):
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "engine"], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        self.lines = []
        self.queue = queue.Queue()
        self.reader = Thread(target=self.read_stdout, daemon=True)
        self.reader.start()
        self.addCleanup(self.close_process)
        self.send("uci")
        self.until("uciok")

    def read_stdout(self):
        for line in self.process.stdout:
            self.queue.put(line.strip())
        self.queue.put(None)

    def send(self, command):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def until(self, prefix, timeout=5):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.fail(f"No {prefix!r} within {timeout}s: {self.lines!r}")
            try:
                line = self.queue.get(timeout=remaining)
            except queue.Empty:
                self.fail(f"No {prefix!r} within {timeout}s: {self.lines!r}")
            if line is None:
                self.fail(f"Engine exited before {prefix!r}: {self.lines!r}")
            self.lines.append(line)
            if line.startswith(prefix):
                return line

    def close_process(self):
        if self.process.poll() is None:
            try:
                self.send("quit")
            except (OSError, ValueError):
                pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.reader.join(timeout=1)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()

    def test_all_finite_limits_remain_ready_and_stop_with_one_legal_move(self):
        legal = {move.uci() for move in generate_legal_moves(Board())}
        for command in (
            "go movetime 60000", "go depth 64", "go depth 64 nodes 100000000",
            "go wtime 600000 btime 600000 winc 0 binc 0",
        ):
            with self.subTest(command=command):
                start = len(self.lines)
                self.send("position startpos")
                self.send(command)
                self.send("isready")
                self.until("readyok")
                self.send("stop")
                self.send("isready")
                self.until("readyok")
                moves = [line for line in self.lines[start:] if line.startswith("bestmove ")]
                self.assertEqual(len(moves), 1, self.lines[start:])
                self.assertIn(moves[0].split()[1], legal)
                self.send("stop")
                self.send("isready")
                self.until("readyok")
                self.assertEqual(sum(line.startswith("bestmove ") for line in self.lines[start:]), 1)

    def test_natural_completion_is_published_while_input_stays_open(self):
        self.send("go depth 1")
        best = self.until("bestmove ")
        self.assertNotEqual(best, "bestmove 0000")
        self.send("stop")
        self.send("isready")
        self.until("readyok")
        self.assertEqual(sum(line.startswith("bestmove ") for line in self.lines), 1)

    def test_infinite_stop_still_returns_one_move(self):
        self.send("go infinite")
        self.send("isready")
        self.until("readyok")
        self.send("stop")
        self.send("isready")
        self.until("readyok")
        self.assertEqual(sum(line.startswith("bestmove ") for line in self.lines), 1)

    def test_eof_cancels_an_active_search_and_exits(self):
        self.send("go depth 64")
        self.send("isready")
        self.until("readyok")
        self.process.stdin.close()
        self.assertEqual(self.process.wait(timeout=5), 0)


if __name__ == "__main__":
    unittest.main()
