"""Draw-sensitive TT reuse: clocks, reversible histories and null-move isolation."""

import unittest
from unittest.mock import patch

from engine.board import Board
from engine.movegen import find_legal_move
from engine.search import MATE_SCORE, TT_EXACT, Searcher

CYCLE_FEN = "6nk/8/8/8/8/8/8/1Q2K1N1 w - - 0 1"
CYCLE = ("g1f3", "g8f6", "f3g1", "f6g8")


def play(board, moves):
    for text in moves:
        board.make_move(find_legal_move(board, text))
    return board


class TTContextTests(unittest.TestCase):
    """Small table/board checks; these do not run an engine search."""

    def setUp(self):
        self.searcher = Searcher(hash_mb=1)

    def test_clock_mismatch_keeps_only_the_move_hint(self):
        first = Board("7k/8/8/8/8/8/8/KQ6 w - - 0 1")
        late = Board("7k/8/8/8/8/8/8/KQ6 w - - 98 1")
        move = find_legal_move(first, "a1a2")
        self.searcher._store(first, 4, TT_EXACT, 888, move)
        self.assertEqual(first.zobrist_hash, late.zobrist_hash)
        self.assertEqual(self.searcher._probe(first)[0].score, 888)
        entry, hint = self.searcher._probe(late)
        self.assertIsNone(entry)
        self.assertEqual(hint, move)

    def test_same_fen_and_clock_with_different_known_history_cannot_reuse_score(self):
        played = play(Board(CYCLE_FEN), CYCLE)
        fresh = Board(played.to_fen())
        self.assertEqual(played.zobrist_hash, fresh.zobrist_hash)
        self.assertEqual(played.halfmove_clock, fresh.halfmove_clock)
        self.assertFalse(played.is_threefold_repetition())
        self.searcher._store(fresh, 4, TT_EXACT, 900, None)
        self.assertIsNone(self.searcher._probe(played)[0])

    def test_history_snapshot_survives_make_and_unmake(self):
        board = play(Board(CYCLE_FEN), CYCLE)
        self.searcher._store(board, 2, TT_EXACT, 100, None)
        entry = self.searcher._probe(board)[0]
        context = entry.context
        board.make_move(find_legal_move(board, CYCLE[0]))
        self.assertEqual(entry.context, context)
        board.unmake_move()
        self.assertIs(self.searcher._probe(board)[0], entry)

    def test_pawn_move_drops_irrelevant_prior_history(self):
        board = play(Board(), CYCLE)
        play(board, ("e2e4",))
        fresh = Board(board.to_fen())
        self.assertEqual(board.halfmove_clock, 0)
        self.searcher._store(board, 2, TT_EXACT, 20, None)
        self.assertEqual(self.searcher._probe(fresh)[0].score, 20)

    def test_new_context_can_replace_a_deeper_old_context(self):
        first = Board("7k/8/8/8/8/8/8/KQ6 w - - 0 1")
        late = Board("7k/8/8/8/8/8/8/KQ6 w - - 98 1")
        self.searcher._store(first, 8, TT_EXACT, 888, None)
        self.searcher._store(late, 1, TT_EXACT, 0, None)
        self.assertEqual(self.searcher._probe(late)[0].score, 0)
        self.assertIsNone(self.searcher._probe(first)[0])

    def test_depth_preference_is_retained_for_the_same_context(self):
        board = Board()
        self.searcher._store(board, 4, TT_EXACT, 40, None)
        self.searcher._store(board, 1, TT_EXACT, 10, None)
        self.assertEqual(self.searcher._probe(board)[0].score, 40)

    def test_null_subtree_neither_consumes_nor_replaces_a_real_score(self):
        board = Board()
        board.make_null_move()
        legal_fen = Board(board.to_fen())
        move = find_legal_move(legal_fen, "g8f6")
        self.searcher._store(legal_fen, 2, TT_EXACT, 30, move)
        entry, hint = self.searcher._probe(board)
        self.assertIsNone(entry)
        self.assertEqual(hint, move)
        size = self.searcher.tt_size
        self.searcher._store(board, 8, TT_EXACT, 999, None)
        self.assertEqual(self.searcher.tt_size, size)
        self.assertEqual(self.searcher._probe(legal_fen)[0].score, 30)
        board.unmake_null_move()
        self.assertEqual(board.to_fen(), Board().to_fen())

    def test_nonzero_contempt_separates_root_perspectives(self):
        board = Board(CYCLE_FEN)
        self.searcher.contempt = 15
        self.searcher._root_color = 1
        self.searcher._store(board, 2, TT_EXACT, 100, None)
        self.searcher._root_color = -1
        self.assertIsNone(self.searcher._probe(board)[0])
        self.searcher.contempt = 0
        self.searcher._store(board, 2, TT_EXACT, 100, None)
        self.searcher._root_color = 1
        self.assertEqual(self.searcher._probe(board)[0].score, 100)


class TTDrawRegressionTests(unittest.TestCase):
    """Real searches belong to the Kaggle suite, not local smoke checks."""

    def test_warm_clock_zero_table_does_not_hide_the_fifty_move_draw(self):
        early = Board("7k/8/8/8/8/8/8/KQ6 w - - 0 1")
        late = Board("7k/8/8/8/8/8/8/KQ6 w - - 98 1")
        searcher = Searcher(null_move=False, lmr=False)
        self.assertGreater(searcher.search(early, depth=2).score, 0)
        warm = searcher.search(late, depth=2)
        cold = Searcher(null_move=False, lmr=False).search(late, depth=2)
        disabled = Searcher(hash_mb=0, null_move=False, lmr=False).search(late, depth=2)
        self.assertEqual((warm.score, cold.score, disabled.score), (0, 0, 0))

    def test_draw_from_a_late_clock_does_not_poison_an_early_clock(self):
        early = Board("7k/8/8/8/8/8/8/KQ6 w - - 0 1")
        late = Board("7k/8/8/8/8/8/8/KQ6 w - - 98 1")
        searcher = Searcher(null_move=False, lmr=False)
        self.assertEqual(searcher.search(late, depth=2).score, 0)
        warm = searcher.search(early, depth=2)
        disabled = Searcher(hash_mb=0, null_move=False, lmr=False).search(early, depth=2)
        self.assertEqual(warm.score, disabled.score)
        self.assertGreater(warm.score, 0)

    def forced_cycle(self):
        # A controlled tree of actual legal moves isolates draw propagation:
        # with a prior cycle the leaf repeats three times, without it only twice.
        board = Board(CYCLE_FEN)
        forced = {}
        for text in CYCLE:
            move = find_legal_move(board, text)
            forced[board.zobrist_hash] = move
            board.make_move(move)

        def moves(position, captures_only=False, known_in_check=None, *, context=None):
            return iter(()) if captures_only else iter((forced[position.zobrist_hash],))

        return patch("engine.search.generate_legal_moves", side_effect=moves)

    def test_descendant_repetition_is_not_reused_under_a_different_history(self):
        repeated = play(Board(CYCLE_FEN), CYCLE)
        fresh = Board(repeated.to_fen())
        before = (repeated.to_fen(), repeated.zobrist_hash, tuple(repeated.position_hashes))
        searcher = Searcher(null_move=False, lmr=False, killers=False)
        with self.forced_cycle():
            winning = searcher._negamax(fresh, 4, -MATE_SCORE, MATE_SCORE, 0)
            cached = searcher._negamax(repeated, 4, -MATE_SCORE, MATE_SCORE, 0)
            oracle = Searcher(hash_mb=0, null_move=False, lmr=False, killers=False)._negamax(
                repeated, 4, -MATE_SCORE, MATE_SCORE, 0)
        self.assertGreater(winning, 0)
        self.assertEqual((cached, oracle), (0, 0))
        self.assertEqual(before, (repeated.to_fen(), repeated.zobrist_hash, tuple(repeated.position_hashes)))

    def test_repetition_draw_does_not_poison_a_fresh_history(self):
        repeated = play(Board(CYCLE_FEN), CYCLE)
        fresh = Board(repeated.to_fen())
        searcher = Searcher(null_move=False, lmr=False, killers=False)
        with self.forced_cycle():
            draw = searcher._negamax(repeated, 4, -MATE_SCORE, MATE_SCORE, 0)
            cached = searcher._negamax(fresh, 4, -MATE_SCORE, MATE_SCORE, 0)
            oracle = Searcher(hash_mb=0, null_move=False, lmr=False, killers=False)._negamax(
                fresh, 4, -MATE_SCORE, MATE_SCORE, 0)
        self.assertEqual(draw, 0)
        self.assertGreater(cached, 0)
        self.assertEqual(cached, oracle)


if __name__ == "__main__":
    unittest.main()
