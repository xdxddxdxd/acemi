"""Small checks for the offline analysis helpers."""

import unittest

import chess

from tools import analyze_report
from tools.analyze_games import _material, _phase, _result_for, game_signature

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
KQK = "4k3/8/8/8/8/8/8/3QK3 w - - 0 1"
KPK = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"


class AnalyzeHelpersTests(unittest.TestCase):
    def test_material_balance_at_start_is_zero(self) -> None:
        self.assertEqual(_material(chess.Board(START)), 0)

    def test_phase_labels(self) -> None:
        self.assertEqual(_phase(chess.Board(START), 1), "opening")
        self.assertEqual(_phase(chess.Board(KPK), 30), "endgame")

    def test_result_for_colour(self) -> None:
        self.assertEqual(_result_for("white", "1-0"), "win")
        self.assertEqual(_result_for("black", "1-0"), "loss")
        self.assertEqual(_result_for("white", "1/2-1/2"), "draw")

    def test_signature_uses_the_full_pgn_line(self) -> None:
        self.assertEqual(game_signature({"pgn_moves": ["e2e4", "e7e5"], "result": "1-0"}),
                         (("e2e4", "e7e5"), "1-0"))

    def test_opening_helpers(self) -> None:
        self.assertEqual(analyze_report.opening_line("Ruy Lopez: e2e4 e7e5"), "e2e4 e7e5")
        self.assertEqual(analyze_report.opening_name("Ruy Lopez: e2e4 e7e5"), "Ruy Lopez")

    def test_theme_labels_for_basic_mates(self) -> None:
        row = {"fen": KQK, "phase": "endgame", "category": "positional"}
        self.assertEqual(analyze_report.theme_of(row, None), "KQK (mat dönüştürme)")
        row = {"fen": KPK, "phase": "endgame", "category": "positional"}
        self.assertEqual(analyze_report.theme_of(row, None), "KPK")


if __name__ == "__main__":
    unittest.main()
