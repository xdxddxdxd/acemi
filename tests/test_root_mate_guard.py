"""Fast bounded regressions; the complete test suite and matches run in Kaggle."""

import copy
from threading import Event
import unittest
from unittest.mock import patch

from engine.board import Board, Move, parse_square
from engine.movegen import find_legal_move, generate_legal_moves
from engine.search import Searcher, _RootGuardStopped
from engine.uci import UciSession

CRITICAL_FEN = "rnb2rk1/ppp2ppp/8/1N1p4/1b1PnB1q/P7/1P1NPPPP/R2QKB1R w KQ - 1 10"


class RootGuardFlowTests(unittest.TestCase):
    """Mock probes only: no recursive search, match or real tactical screen."""

    def setUp(self):
        self.board = Board()
        self.before = copy.deepcopy(self.board.__dict__)
        self.moves = list(generate_legal_moves(self.board))[:4]
        self.threat = Move(parse_square("b8"), parse_square("a6"))
        self.searcher = Searcher(root_mate_guard=True)

    def screen(self, outcomes):
        with patch.object(self.searcher, "_find_mating_reply", side_effect=outcomes):
            result = self.searcher._guard_root_moves(self.board, self.moves, 0)
        self.assertEqual(self.board.__dict__, self.before)
        return result

    def test_no_threat_preserves_the_original_list(self):
        self.assertIs(self.screen([None]), self.moves)
        self.assertFalse(self.searcher.root_guard_stats["triggered"])

    def test_only_proven_mate_losses_are_removed_with_a_safe_alternative(self):
        result = self.screen([self.threat, self.threat, None, self.threat, None])
        self.assertEqual(result, [self.moves[1], self.moves[3]])
        self.assertTrue(self.searcher.root_guard_stats["complete"])

    def test_all_losing_moves_are_retained(self):
        self.assertIs(self.screen([self.threat] * 5), self.moves)

    def test_partial_screen_keeps_unknown_moves_and_restores_the_board(self):
        result = self.screen([self.threat, self.threat, None, _RootGuardStopped()])
        self.assertEqual(result, [self.moves[1], self.moves[2], self.moves[3]])
        self.assertFalse(self.searcher.root_guard_stats["complete"])
        self.assertEqual(self.searcher.root_guard_stats["unknown_moves"], 2)

    def test_interrupted_pass_does_not_leak_a_null_move(self):
        self.assertIs(self.screen([_RootGuardStopped()]), self.moves)

    def test_soft_time_limit_is_inside_original_deadline(self):
        self.searcher._deadline = 0.1
        with patch("engine.search.time.monotonic", side_effect=[0, .021, .021, .022]), \
             patch.object(self.searcher, "_find_mating_reply") as probe:
            self.assertIs(self.searcher._guard_root_moves(self.board, self.moves, 0), self.moves)
        probe.assert_not_called()
        self.assertEqual(self.board.__dict__, self.before)

    def test_node_limit_is_shared_with_main_search(self):
        self.searcher._nodes_limit = 1
        with patch.object(self.searcher, "_find_mating_reply") as probe:
            self.assertIs(self.searcher._guard_root_moves(self.board, self.moves, 0), self.moves)
        self.assertEqual(self.searcher.nodes, 1)
        probe.assert_not_called()

    def test_external_stop_does_not_start_a_probe(self):
        self.searcher._stop_event = Event()
        self.searcher._stop_event.set()
        with patch.object(self.searcher, "_find_mating_reply") as probe:
            self.assertIs(self.searcher._guard_root_moves(self.board, self.moves, 0), self.moves)
        probe.assert_not_called()

    def test_prospective_draw_contexts_skip_pruning_entirely(self):
        clock = Board(self.board.to_fen().replace(" 0 1", " 98 1"))
        cycle = Board()
        for move in ("g1f3", "g8f6", "f3g1", "f6g8"):
            cycle.make_move(find_legal_move(cycle, move))
        for board in (clock, cycle):
            before = copy.deepcopy(board.__dict__)
            moves = list(generate_legal_moves(board))
            with patch.object(self.searcher, "_find_mating_reply") as probe:
                self.assertIs(self.searcher._guard_root_moves(board, moves, 0), moves)
            probe.assert_not_called()
            self.assertTrue(self.searcher.root_guard_stats["skipped_draw_context"])
            self.assertEqual(board.__dict__, before)

    def test_reply_exception_unwinds_its_move(self):
        with patch("engine.search.generate_legal_moves", side_effect=[iter([self.moves[0]]), RuntimeError("fixture")]), \
             patch("engine.search.order_moves"), patch.object(self.board, "in_check", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                self.searcher._find_mating_reply(self.board, lambda: None)
        self.assertEqual(self.board.__dict__, self.before)

    def test_default_is_off_and_uci_toggle_invalidates_tt(self):
        session = UciSession()
        self.assertFalse(session.searcher.use_root_mate_guard)
        self.assertIn("option name RootMateGuard type check default false", session.handle_line("uci"))
        from engine.search import TT_EXACT
        session.searcher._store(session.board, 2, TT_EXACT, 7, None)
        session.handle_line("setoption name RootMateGuard value true")
        self.assertTrue(session.searcher.use_root_mate_guard)
        self.assertEqual(session.searcher.tt_size, 0)

    def test_disabled_path_never_calls_the_screen(self):
        searcher = Searcher()
        with patch.object(searcher, "_guard_root_moves") as screen, \
             patch.object(searcher, "_search_root", return_value=(self.moves[0], 7)):
            result = searcher.search(self.board, depth=1)
        screen.assert_not_called()
        self.assertEqual(result.score, 7)


class RootGuardLegalRegressionTests(unittest.TestCase):
    """Bounded legal probes and two brief searches; also included in Kaggle."""

    @staticmethod
    def allows_mate(board):
        import chess
        if board.outcome(claim_draw=True) is not None:
            return False
        for reply in list(board.legal_moves):
            board.push(reply)
            mate = board.is_checkmate()
            board.pop()
            if mate:
                return True
        return False

    def test_critical_screen_agrees_with_independent_oracle_and_colour_mirror(self):
        import chess
        for oracle in (chess.Board(CRITICAL_FEN), chess.Board(CRITICAL_FEN).mirror()):
            board = Board(oracle.fen())
            before = copy.deepcopy(board.__dict__)
            moves = list(generate_legal_moves(board))
            expected = set()
            for move in list(oracle.legal_moves):
                oracle.push(move)
                loses = self.allows_mate(oracle)
                oracle.pop()
                if not loses:
                    expected.add(move.uci())
            self.assertTrue(expected)
            self.assertLess(len(expected), len(moves))
            searcher = Searcher(root_mate_guard=True)
            screened = searcher._guard_root_moves(board, moves, 0)
            self.assertEqual({m.uci() for m in screened}, expected)
            self.assertEqual(board.__dict__, before)
            self.assertTrue(searcher.root_guard_stats["complete"])

    def test_known_capture_loses_and_g3_blocks_the_mating_diagonal(self):
        import chess
        oracle = chess.Board(CRITICAL_FEN)
        oracle.push_uci("a3b4")
        oracle.push_uci("h4f2")
        self.assertTrue(oracle.is_checkmate())
        oracle = chess.Board(CRITICAL_FEN)
        oracle.push_uci("g2g3")
        self.assertFalse(self.allows_mate(oracle))

    def test_timed_candidate_avoids_immediate_mate_in_the_critical_position(self):
        import chess
        for milliseconds in (100, 500):
            board = Board(CRITICAL_FEN)
            before = copy.deepcopy(board.__dict__)
            searcher = Searcher(root_mate_guard=True, tt_two_contexts=True)
            result = searcher.search(board, depth=64, movetime_ms=milliseconds)
            self.assertIsNotNone(result.best_move)
            oracle = chess.Board(CRITICAL_FEN)
            oracle.push_uci(result.best_move.uci())
            self.assertFalse(self.allows_mate(oracle))
            self.assertEqual(board.__dict__, before)

