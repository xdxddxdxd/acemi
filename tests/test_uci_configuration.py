"""Configuration isolation and TT invalidation; real search regressions run in Kaggle."""

import random
import unittest
from unittest.mock import patch

from engine.board import Board
from engine.eval.base import evaluate
from engine.eval.classic import FLAGS, EvalFlags
from engine.movegen import find_legal_move
from engine.search import MATE_SCORE, TT_EXACT, Searcher
from engine.uci import CHECK_OPTIONS, EVAL_OPTIONS, SPIN_LIMITS, UciSession

PAWN = "7k/8/8/8/4P3/8/8/K7 w - - 0 1"
BISHOPS = "7k/8/8/8/8/8/8/KBB5 w - - 0 1"


class FlagFixture(unittest.TestCase):
    def setUp(self):
        saved = FLAGS.signature()
        self.addCleanup(self.restore_flags, saved)
        self.restore_flags((False,) * len(EvalFlags.__slots__))

    @staticmethod
    def restore_flags(values):
        for name, value in zip(EvalFlags.__slots__, values):
            setattr(FLAGS, name, value)


def seed_table(session):
    session.searcher._store(session.board, 2, TT_EXACT, 777, None)
    return session.searcher._probe(session.board)[0]


class UciConfigurationTests(FlagFixture):
    """No recursive search, engine process, benchmark or match is used here."""

    def test_each_eval_change_clears_only_its_sessions_table(self):
        for option, attribute in EVAL_OPTIONS.items():
            with self.subTest(option=option):
                session, other = UciSession(), UciSession()
                seed_table(session)
                other_entry = seed_table(other)
                self.assertEqual(session.handle_line(f"setoption name {option} value true"), [])
                self.assertTrue(getattr(session.eval_flags, attribute))
                self.assertEqual(session.searcher.tt_size, 0)
                self.assertFalse(getattr(other.eval_flags, attribute))
                self.assertIs(other.searcher._probe(other.board)[0], other_entry)
                self.assertEqual(FLAGS.signature(), (False,) * len(EvalFlags.__slots__))
                seed_table(session)
                session.handle_line(f"setoption name {option} value false")
                self.assertEqual(session.searcher.tt_size, 0)

    def test_each_search_policy_change_invalidates_the_table(self):
        for option, attribute in CHECK_OPTIONS.items():
            with self.subTest(option=option):
                session = UciSession()
                previous = getattr(session.searcher, attribute)
                seed_table(session)
                value = str(not previous).lower()
                self.assertEqual(session.handle_line(f"setoption name {option} value {value}"), [])
                self.assertEqual(getattr(session.searcher, attribute), not previous)
                self.assertEqual(session.searcher.tt_size, 0)

    def test_repeating_eval_and_search_values_preserves_valid_entries(self):
        session = UciSession()
        for option in (*EVAL_OPTIONS, *CHECK_OPTIONS):
            with self.subTest(option=option):
                session.handle_line(f"setoption name {option} value true")
                entry = seed_table(session)
                session.handle_line(f"setoption name {option} value true")
                self.assertIs(session.searcher._probe(session.board)[0], entry)

    def test_bad_boolean_changes_neither_configuration_nor_cache(self):
        session = UciSession()
        for option in (*EVAL_OPTIONS, *CHECK_OPTIONS):
            with self.subTest(option=option):
                configuration = session.searcher._configuration_key()
                entry = seed_table(session)
                reply = session.handle_line(f"setoption name {option} value maybe")
                self.assertTrue(reply[0].startswith("info string"))
                self.assertEqual(session.searcher._configuration_key(), configuration)
                self.assertIs(session.searcher._probe(session.board)[0], entry)

    def test_new_session_does_not_inherit_legacy_global_flags(self):
        FLAGS.passed_pawns = True
        session = UciSession()
        self.assertEqual(session.eval_flags.signature(), (False,) * len(EvalFlags.__slots__))
        self.assertTrue(FLAGS.passed_pawns)
        self.assertEqual(evaluate(Board(PAWN), session.eval_flags), evaluate(Board(PAWN), EvalFlags()))

    def test_explicit_evaluators_and_sessions_are_independent(self):
        first, second = UciSession(), UciSession()
        first.handle_line("setoption name EvalPassedPawns value true")
        self.assertGreater(evaluate(Board(PAWN), first.eval_flags), evaluate(Board(PAWN), second.eval_flags))
        self.assertFalse(second.eval_flags.passed_pawns)
        self.assertEqual(FLAGS.signature(), (False,) * len(EvalFlags.__slots__))
        self.assertEqual(evaluate(Board(PAWN)), evaluate(Board(PAWN), second.eval_flags))

    def test_contempt_change_invalidates_but_same_value_does_not(self):
        session = UciSession()
        seed_table(session)
        session.handle_line("setoption name Contempt value 15")
        self.assertEqual(session.searcher.tt_size, 0)
        entry = seed_table(session)
        session.handle_line("setoption name Contempt value 15")
        self.assertIs(session.searcher._probe(session.board)[0], entry)

    def test_spin_ranges_match_the_advertised_protocol(self):
        lines = UciSession().handle_line("uci")
        for name, bounds in SPIN_LIMITS.items():
            line = next(line for line in lines if line.lower().startswith(f"option name {name} type spin "))
            parts = line.split()
            advertised = (int(parts[parts.index("min") + 1]), int(parts[parts.index("max") + 1]))
            self.assertEqual(bounds, advertised)

    def test_invalid_spin_values_do_not_apply_or_destroy_the_cache(self):
        session = UciSession()
        invalid = {
            "Hash": ("0", "4097", "-1", "not-an-int"),
            "Threads": ("0", "2", "-1", "1.5"),
            "Seed": ("-1", "2147483648", "NaN"),
            "NextIterationPct": ("49", "501", "x"),
            "Contempt": ("-1", "201", "x"),
        }
        for option, values in invalid.items():
            for value in values:
                with self.subTest(option=option, value=value):
                    before = (session.hash_mb, session.threads, session.seed, session.rng.getstate(),
                              session.searcher.tt_capacity, session.searcher.contempt,
                              session.searcher.next_iteration_factor)
                    entry = seed_table(session)
                    reply = session.handle_line(f"setoption name {option} value {value}")
                    self.assertTrue(reply[0].startswith("info string"))
                    after = (session.hash_mb, session.threads, session.seed, session.rng.getstate(),
                             session.searcher.tt_capacity, session.searcher.contempt,
                             session.searcher.next_iteration_factor)
                    self.assertEqual(before, after)
                    self.assertIs(session.searcher._probe(session.board)[0], entry)

    def test_supported_spin_endpoints_are_accepted(self):
        session = UciSession()
        for option, values in (
            ("Hash", (1, 4096)), ("Threads", (1,)), ("Seed", (0, 2147483647)),
            ("NextIterationPct", (50, 500)), ("Contempt", (0, 200)),
        ):
            for value in values:
                with self.subTest(option=option, value=value):
                    self.assertEqual(session.handle_line(f"setoption name {option} value {value}"), [])
        # Hash capacity is an integer limit; these tests never fill a large table.
        self.assertEqual(session.searcher.tt_capacity, 4096 * 5000)
        self.assertEqual(session.seed, 2147483647)
        self.assertEqual(session.searcher.next_iteration_factor, 5.0)

    def test_same_hash_preserves_cache_and_changed_hash_resizes(self):
        session = UciSession()
        entry = seed_table(session)
        session.handle_line("setoption name Hash value 16")
        self.assertIs(session.searcher._probe(session.board)[0], entry)
        session.handle_line("setoption name Hash value 1")
        self.assertEqual(session.searcher.tt_size, 0)
        self.assertEqual(session.searcher.tt_capacity, 5000)

    def test_seed_and_time_policy_do_not_invalidate_node_scores(self):
        session = UciSession()
        entry = seed_table(session)
        session.handle_line("setoption name Seed value 7")
        session.handle_line("setoption name NextIterationPct value 110")
        session.handle_line("setoption name Threads value 1")
        self.assertIs(session.searcher._probe(session.board)[0], entry)
        self.assertEqual(session.rng.random(), random.Random(7).random())

    def test_setting_the_same_seed_still_resets_the_random_stream(self):
        session = UciSession()
        session.rng.random()
        entry = seed_table(session)
        session.handle_line("setoption name Seed value 1")
        self.assertEqual(session.rng.random(), random.Random(1).random())
        self.assertIs(session.searcher._probe(session.board)[0], entry)

    def test_public_search_detects_changed_explicit_configuration(self):
        flags = EvalFlags()
        searcher, board = Searcher(eval_flags=flags), Board()
        move = find_legal_move(board, "e2e4")
        searcher._store(board, 2, TT_EXACT, 777, None)
        flags.passed_pawns = True
        with patch.object(searcher, "clear_tt", wraps=searcher.clear_tt) as cleared:
            # Stub the root: exercise configuration entry points, not real search.
            with patch.object(searcher, "_search_root", return_value=(move, 0)):
                searcher.search(board, depth=1)
                searcher.search(board, depth=1)
            self.assertEqual(cleared.call_count, 1)

    def test_public_search_detects_changed_legacy_global_configuration(self):
        searcher, board = Searcher(), Board()
        move = find_legal_move(board, "e2e4")
        searcher._store(board, 2, TT_EXACT, 777, None)
        FLAGS.bishop_pair = True
        with patch.object(searcher, "clear_tt", wraps=searcher.clear_tt) as cleared:
            with patch.object(searcher, "_search_root", return_value=(move, 0)):
                searcher.search(board, depth=1)
            cleared.assert_called_once()

    def test_public_search_detects_a_replaced_legacy_default_object(self):
        searcher, board = Searcher(), Board()
        move = find_legal_move(board, "e2e4")
        searcher._store(board, 2, TT_EXACT, 777, None)
        replacement = EvalFlags()
        replacement.bishop_pair = True
        with patch("engine.eval.classic.FLAGS", replacement):
            with patch.object(searcher, "clear_tt", wraps=searcher.clear_tt) as cleared:
                with patch.object(searcher, "_search_root", return_value=(move, 0)):
                    searcher.search(board, depth=1)
                cleared.assert_called_once()


class ConfigurationSearchRegressionTests(FlagFixture):
    """Real search cases for Kaggle; excluded from local configuration smoke checks."""

    def check_uci_toggle(self, fen, option):
        session = UciSession()
        session.board = Board(fen)
        before = session.searcher._negamax(session.board, 1, -MATE_SCORE, MATE_SCORE, 1)
        self.assertGreater(session.searcher.tt_size, 0)
        self.assertEqual(session.handle_line(f"setoption name {option} value true"), [])
        warm = session.searcher._negamax(session.board, 1, -MATE_SCORE, MATE_SCORE, 1)
        fresh = UciSession()
        fresh.board = Board(fen)
        fresh.handle_line(f"setoption name {option} value true")
        cold = fresh.searcher._negamax(fresh.board, 1, -MATE_SCORE, MATE_SCORE, 1)
        self.assertGreater(warm, before)
        self.assertEqual(warm, cold)

    def test_passed_pawn_option_does_not_reuse_the_old_score(self):
        self.check_uci_toggle(PAWN, "EvalPassedPawns")

    def test_bishop_pair_option_does_not_reuse_the_old_score(self):
        self.check_uci_toggle(BISHOPS, "EvalBishopPair")

    def test_explicit_flag_mutation_matches_a_tt_disabled_oracle(self):
        flags, board = EvalFlags(), Board(PAWN)
        searcher = Searcher(eval_flags=flags, null_move=False, lmr=False)
        before = searcher.search(board, depth=2)
        flags.passed_pawns = True
        warm = searcher.search(board, depth=2)
        oracle = Searcher(hash_mb=0, eval_flags=flags, null_move=False, lmr=False).search(board, depth=2)
        self.assertGreater(warm.score, before.score)
        self.assertEqual(warm.score, oracle.score)

    def test_legacy_global_mutation_matches_a_tt_disabled_oracle(self):
        board = Board(PAWN)
        searcher = Searcher(null_move=False, lmr=False)
        before = searcher.search(board, depth=2)
        FLAGS.passed_pawns = True
        warm = searcher.search(board, depth=2)
        oracle = Searcher(hash_mb=0, null_move=False, lmr=False).search(board, depth=2)
        self.assertGreater(warm.score, before.score)
        self.assertEqual(warm.score, oracle.score)


if __name__ == "__main__":
    unittest.main()
