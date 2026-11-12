"""Longer equivalence checks; execute only in the Kaggle correctness suite."""
import itertools
import random
import unittest
from engine.board import Board
from engine.eval.classic import EvalFlags, evaluate_classic
from engine.movegen import generate_legal_moves
from engine.search import Searcher


class PackedEvalSearchTests(unittest.TestCase):
    def test_legal_games_undo_null_and_all_flag_combinations(self):
        rng = random.Random(381)
        for game in range(4):
            board = Board()
            for ply in range(64):
                for bits in itertools.product((False, True), repeat=5):
                    flags = EvalFlags()
                    for name, value in zip(EvalFlags.__slots__[:5], bits):
                        setattr(flags, name, value)
                    expected = evaluate_classic(board, flags)
                    flags.packed_base = True
                    self.assertEqual(evaluate_classic(board, flags), expected)
                board.make_null_move()
                flags = EvalFlags()
                plain = evaluate_classic(board, flags)
                flags.packed_base = True
                self.assertEqual(evaluate_classic(board, flags), plain)
                board.unmake_null_move()
                moves = list(generate_legal_moves(board))
                if not moves:
                    break
                board.make_move(rng.choice(moves))
            while board.undo_stack:
                board.unmake_move()
                restored = Board(board.to_fen())
                for packed in (False, True):
                    flags = EvalFlags()
                    flags.packed_base = packed
                    self.assertEqual(evaluate_classic(board, flags), evaluate_classic(restored, flags))

    def test_fixed_work_search_and_special_moves_are_identical(self):
        fens = ['r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1',
                '7k/8/8/3pP3/8/8/8/K7 w - d6 0 1',
                'r6k/1P6/8/8/8/8/8/7K w - - 0 1']
        for fen in fens:
            results = []
            for packed in (False, True):
                flags = EvalFlags()
                flags.packed_base = packed
                board = Board(fen)
                searcher = Searcher(eval_flags=flags, tt_two_contexts=True)
                for repeat in range(2):
                    result = searcher.search(board, depth=4, nodes_limit=2500)
                    results.append((packed, repeat, result.best_move, result.score, result.depth, result.nodes))
                    self.assertEqual(board.to_fen(), fen)
            for repeat in range(2):
                self.assertEqual(results[repeat][2:], results[2+repeat][2:])
