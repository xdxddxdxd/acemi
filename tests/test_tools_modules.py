"""Tool-module boundaries: compatibility, serialization and fixture-only CLI routes."""

import contextlib
import gzip
import io
import json
import pickle
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import (
    match, match_config, match_game, match_openings,
    analyze_games, analysis_artifacts, analysis_config, analysis_inputs, analysis_schema,
)
from tests.test_analyze_tools import fake_game, write_cache


class MatchModuleTests(unittest.TestCase):
    def test_old_imports_and_worker_serialization_still_work(self):
        self.assertIs(match.Opening, match_openings.Opening)
        self.assertIs(match.play_game, match_game.play_game)
        self.assertIs(match.parse_option_assignments, match_config.parse_option_assignments)
        self.assertIs(pickle.loads(pickle.dumps(match.play_game)), match_game.play_game)
        opening = match.builtin_openings()[0]
        self.assertEqual(pickle.loads(pickle.dumps(opening)), opening)

    def test_cli_defaults_and_repeatable_option_values(self):
        defaults = match._parse_args([])
        self.assertEqual((defaults.games, defaults.movetime_ms, defaults.hash_mb), (20, 500, 16))
        args = match._parse_args(["--engine-option", "OwnBook=true", "--engine-option", "Hash=32", "--no-record"])
        self.assertTrue(args.no_record)
        self.assertEqual(match.parse_option_assignments(args.engine_option),
                         [["OwnBook", True, True], ["Hash", 32, True]])

    def test_bad_options_exit_before_starting_engines(self):
        with patch.object(match, "UciEngine") as engine, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(match.main(["--engine-option", "missing-value", "--no-record"]), 2)
        engine.assert_not_called()

    def test_opening_loader_keeps_lines_fen_and_error_details(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "openings.txt"
            path.write_text("# fixture\ne2e4 e7e5\n7k/8/8/8/8/8/8/K7 w - - 0 1\n", encoding="utf-8")
            name, rows = match.load_openings(path)
            self.assertEqual(name, "openings")
            self.assertEqual(rows[0].moves, ("e2e4", "e7e5"))
            self.assertEqual(rows[1].start_fen, "7k/8/8/8/8/8/8/K7 w - - 0 1")
            path.write_text("e2e5\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "illegal opening move"):
                match.load_openings(path)

    def test_worker_lifecycle_and_fatal_error_use_mocked_game_body(self):
        job = {"engine_cmd": ["fixture"], "engine_cwd": None,
               "opponent_cmd": ["fixture"], "opponent_cwd": None,
               "engine_options": [], "opponent_options": [], "game_no": 0}
        with patch.object(match_game, "UciEngine") as engine, \
             patch.object(match_game, "_start_engine"), \
             patch.object(match_game, "_play_moves", return_value={"game_no": 1}) as body:
            result = match.play_game(job)
            self.assertEqual(result, {"game_no": 1, "log": []})
            self.assertEqual(engine.return_value.close.call_count, 2)
            body.assert_called_once()
        with patch.object(match_game, "UciEngine") as engine, \
             patch.object(match_game, "_start_engine", side_effect=match_game.EngineSetupError("fixture failure")):
            self.assertEqual(match.play_game(job), {"fatal": "fixture failure", "game_no": 1})
            self.assertEqual(engine.return_value.close.call_count, 2)


class AnalysisModuleTests(unittest.TestCase):
    def test_old_imports_refer_to_the_shared_schema_and_artifacts(self):
        self.assertIs(analyze_games.POSITION_FIELDS, analysis_schema.POSITION_FIELDS)
        self.assertIs(analyze_games.build_manifest, analysis_inputs.build_manifest)
        self.assertIs(analyze_games.seal_part, analysis_artifacts.seal_part)
        self.assertIs(analyze_games.valid_parts, analysis_artifacts.valid_parts)

    def test_aggregate_only_cli_never_launches_an_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_cache(out, fake_game("fixture#1"))
            analyze_games.seal_part(out)
            with patch.object(analyze_games, "_init_worker") as worker, \
                 patch.object(analyze_games.subprocess, "run") as launch, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(analyze_games.main(["--aggregate-only", "--out", str(out)]), 0)
            worker.assert_not_called()
            launch.assert_not_called()
            self.assertEqual(analyze_games.processed_game_ids(out), {"fixture#1"})

    def test_manifest_prefers_counted_duplicates_and_keeps_ab_sf_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, opponent, counted in (("a", "Acemi", 0), ("b", "Acemi", 1), ("c", "Stockfish", 1)):
                run = root / name
                run.mkdir()
                (run / "meta.json").write_text(json.dumps({"opponent": {"name": opponent}}), encoding="utf-8")
                (run / "results.json").write_text(json.dumps({"games": counted}), encoding="utf-8")
                pgn = ('[White "Acemi"]\n[Black "' + opponent + '"]\n[Round "1"]\n'
                       '[Result "1/2-1/2"]\n\n1. e4 e5 1/2-1/2\n')
                with gzip.open(run / "games.pgn.gz", "wt", encoding="utf-8") as stream:
                    stream.write(pgn)
            games, stats = analyze_games.build_manifest(root, {"AB", "SF"})
            self.assertEqual([(game["run_name"], game["run_type"]) for game in games], [("b", "AB"), ("c", "SF")])
            self.assertEqual(games[0]["duplicate_games"], ["a#1"])
            self.assertEqual((stats["games_total"], stats["games_used"], stats["duplicates"]), (3, 2, 1))

    def test_identity_covers_each_extracted_analysis_module(self):
        required = {"analysis_schema.py", "analysis_inputs.py", "analysis_artifacts.py"}
        self.assertTrue(required <= set(analysis_config.ANALYSIS_SOURCES))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "sf"
            binary.write_bytes(b"fixture executable - never launched")
            for name in analysis_config.ANALYSIS_SOURCES:
                (root / name).write_text(name, encoding="utf-8")
            with patch.object(analysis_config, "__file__", str(root / "analysis_config.py")):
                original = analysis_config.analysis_configuration(binary, 10)
                for name in analysis_config.ANALYSIS_SOURCES:
                    path = root / name
                    path.write_text(name + " changed", encoding="utf-8")
                    changed = analysis_config.analysis_configuration(binary, 10)
                    self.assertNotEqual(analysis_config.fingerprint(original), analysis_config.fingerprint(changed), name)
                    path.write_text(name, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
