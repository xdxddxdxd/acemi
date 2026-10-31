"""Small checks for the offline analysis helpers."""

import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

import chess

from tools import analyze_games, analyze_report
from tools.analyze_games import (
    GAME_FIELDS,
    POSITION_FIELDS,
    _material,
    _phase,
    _result_for,
    _tb_wdl,
    aggregate,
    game_signature,
    opening_plies_from,
    outcome_label,
    part_id,
    processed_game_ids,
    seal_part,
    select_recheck_rows,
    valid_parts,
)

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


def fake_game(game_id: str, run_type: str = "AB", blunder: bool = True) -> dict:
    """Cache entry shaped like ``analyze_game`` output, without Stockfish."""
    plies = []
    for ply in range(1, 4):
        row = {field: "" for field in POSITION_FIELDS}
        row.update(
            run_name=game_id.split("#")[0], run_type=run_type, game_no=int(game_id.split("#")[1]),
            game_id=game_id, ply=ply, side="white" if ply % 2 else "black", player="engine",
            is_acemi=True, fen=START, move="e2e4", sf_cp=10, sf_best_move="d2d4",
            cp_loss=200 if (blunder and ply == 2) else 10, piece_count=32, white_pieces=16, black_pieces=16,
            phase="opening", material_balance=0, opening="e2e4 e7e5", game_result="1-0",
            tb_wdl="", label_source="stockfish",
        )
        plies.append(row)
    stats = {field: "" for field in GAME_FIELDS}
    stats.update(
        game_id=game_id, run_name=game_id.split("#")[0], run_type=run_type, game_no=int(game_id.split("#")[1]),
        result="1-0", result_acemi="win", termination="checkmate", opening="e2e4 e7e5", focus_color="white",
        plies=3, opening_plies=10, in_result_sample=True, result_sample_proxy=False, duplicate_count=0,
        final_piece_count=32, end_phase="opening", final_sf_cp=0,
    )
    return {"game_id": game_id, "plies": plies, "game_stats": stats}


def write_cache(out: Path, *games: dict) -> None:
    (out / "cache").mkdir(parents=True, exist_ok=True)
    for index, game in enumerate(games):
        (out / "cache" / f"{index}_{game['game_id'].replace('#', '_')}.json").write_text(
            json.dumps(game), encoding="utf-8"
        )


class OpeningPliesTests(unittest.TestCase):
    def test_first_record_gives_the_forced_line_length(self) -> None:
        self.assertEqual(opening_plies_from({11: {}, 12: {}}, {"Opening": "e2e4 e7e5"}), (10, "first_record"))
        self.assertEqual(opening_plies_from({1: {}}, {}), (0, "first_record"))

    def test_capped_and_header_fallback(self) -> None:
        self.assertEqual(opening_plies_from({60: {}}, {}), (20, "first_record"))
        self.assertEqual(opening_plies_from({}, {"Opening": "Ruy Lopez: e2e4 e7e5 g1f3"}), (3, "header"))
        self.assertEqual(opening_plies_from({}, {"Opening": "e2e4 e7e5"}), (0, "none"))


class LabelTests(unittest.TestCase):
    def test_tablebase_wins_over_stockfish(self) -> None:
        self.assertEqual(outcome_label(0, 2, 1), ("win", "syzygy"))
        self.assertEqual(outcome_label(900, -2, 1), ("loss", "syzygy"))
        self.assertEqual(outcome_label(900, -2, -1), ("win", "syzygy"))

    def test_cursed_and_blessed_count_as_draws(self) -> None:
        self.assertEqual(outcome_label(900, 1, 1), ("draw", "syzygy"))
        self.assertEqual(outcome_label(-900, -1, 1), ("draw", "syzygy"))

    def test_stockfish_thresholds(self) -> None:
        self.assertEqual(outcome_label(200, None, 1), ("win", "stockfish"))
        self.assertEqual(outcome_label(199, None, 1), ("draw", "stockfish"))
        self.assertEqual(outcome_label(200, None, -1), ("loss", "stockfish"))

    def test_no_tablebase_means_no_probe(self) -> None:
        self.assertIsNone(_tb_wdl(chess.Board(KQK)))


class PartTests(unittest.TestCase):
    def test_part_id_ignores_order_and_changes_with_content(self) -> None:
        self.assertEqual(part_id(["a#1", "b#2"]), part_id(["b#2", "a#1"]))
        self.assertNotEqual(part_id(["a#1"]), part_id(["a#1", "b#2"]))

    def test_seal_writes_an_immutable_part_and_clears_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_cache(out, fake_game("r#1"), fake_game("r#2", "SF", blunder=False))
            entry = seal_part(out)
            self.assertEqual(entry["rows"], {"positions": 6, "games": 2, "blunders": 1})
            self.assertEqual(entry["id"], part_id(["r#1", "r#2"]))
            self.assertEqual(list((out / "cache").glob("*.json")), [])
            self.assertEqual(processed_game_ids(out), {"r#1", "r#2"})
            with gzip.open(out / entry["files"]["positions"]["path"], "rt", encoding="utf-8", newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 6)
            # Nothing new to seal: the part is not rewritten.
            before = (out / entry["files"]["positions"]["path"]).stat().st_mtime_ns
            self.assertIsNone(seal_part(out))
            self.assertEqual((out / entry["files"]["positions"]["path"]).stat().st_mtime_ns, before)

    def test_second_chunk_adds_a_second_part(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_cache(out, fake_game("r#1"))
            first = seal_part(out)
            write_cache(out, fake_game("r#2"))
            second = seal_part(out)
            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual(len(valid_parts(out)[0]), 2)
            self.assertEqual(aggregate(out)["games"], 2)

    def test_damaged_part_is_dropped_so_its_games_are_redone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_cache(out, fake_game("r#1"))
            entry = seal_part(out)
            (out / entry["files"]["positions"]["path"]).write_bytes(b"damaged")
            parts, problems = valid_parts(out)
            self.assertEqual(parts, [])
            self.assertEqual(len(problems), 1)
            self.assertEqual(processed_game_ids(out), set())

    def test_missing_manifest_means_nothing_is_processed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(processed_game_ids(Path(directory)), set())

    def test_aggregate_merges_small_files_and_categorises_blunders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_cache(out, fake_game("r#1"), fake_game("r#2", "SF"))
            seal_part(out)
            summary = aggregate(out)
            self.assertEqual((summary["games"], summary["positions"], summary["blunders"]), (2, 6, 2))
            with (out / "blunders.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual({row["category"] for row in rows}, {"positional"})
            self.assertEqual((out / "processed_games.txt").read_text(encoding="utf-8").split(), ["r#1", "r#2"])
            self.assertFalse((out / "positions.csv.gz").exists())

    def test_report_reads_parts_and_builds_on_synthetic_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_cache(out, fake_game("r#1"), fake_game("s#1", "SF"))
            seal_part(out)
            aggregate(out)
            self.assertEqual(len(analyze_report.read_positions(out)), 6)
            self.assertEqual(analyze_report.main(["--dir", str(out)]), 0)
            self.assertIn("A. Açılış kitabı", (out / "REPORT.md").read_text(encoding="utf-8"))


class RecheckSampleTests(unittest.TestCase):
    @staticmethod
    def rows(ab_games: int, sf_games: int, per_game: int = 3) -> list[dict]:
        rows = []
        for kind, count in (("AB", ab_games), ("SF", sf_games)):
            for game in range(count):
                for ply in range(per_game):
                    rows.append({"run_type": kind, "game_id": f"{kind}#{game}", "ply": str(11 + ply)})
        return rows

    def test_stratified_capped_per_game_and_deterministic(self) -> None:
        rows = self.rows(40, 40)
        sample = select_recheck_rows(rows, limit=50)
        self.assertEqual(sample, select_recheck_rows(rows, limit=50))
        self.assertEqual(len(sample), 50)
        self.assertEqual(sum(1 for row in sample if row["run_type"] == "AB"), 25)
        per_game = {}
        for row in sample:
            per_game[row["game_id"]] = per_game.get(row["game_id"], 0) + 1
        self.assertLessEqual(max(per_game.values()), 2)

    def test_scarce_type_is_topped_up_from_the_other(self) -> None:
        sample = select_recheck_rows(self.rows(40, 3), limit=50)
        self.assertEqual(sum(1 for row in sample if row["run_type"] == "SF"), 6)
        self.assertEqual(len(sample), 50)

    def test_seed_changes_the_sample(self) -> None:
        rows = self.rows(40, 40)
        self.assertNotEqual(select_recheck_rows(rows, seed=1), select_recheck_rows(rows, seed=2))


if __name__ == "__main__":
    unittest.main()
