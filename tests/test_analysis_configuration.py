"""Analysis provenance/resume regressions, using fixtures and mocked evaluation only."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import analyze_games as analysis, analyze_report
from tools.analysis_config import (
    active_fingerprint, analysis_configuration, fingerprint, prepare_output,
)
from tests.test_analyze_tools import fake_game, write_cache


class AnalysisIdentityTests(unittest.TestCase):
    def test_content_changes_invalidate_but_relocation_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "sf"
            binary.write_bytes(b"engine-v1")
            config = analysis_configuration(binary, 10)
            relocated = root / "other-sf"
            relocated.write_bytes(binary.read_bytes())
            self.assertEqual(config, analysis_configuration(relocated, 10))
            self.assertNotEqual(fingerprint(config), fingerprint(analysis_configuration(binary, 11)))
            binary.write_bytes(b"engine-v2")
            self.assertNotEqual(fingerprint(config), fingerprint(analysis_configuration(binary, 10)))
            for key in ("analysis_sources", "python_chess_version", "stockfish_options"):
                changed = copy.deepcopy(config)
                changed[key] = "changed"
                self.assertNotEqual(fingerprint(config), fingerprint(changed))

    def test_syzygy_inventory_and_content_are_part_of_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "sf"
            binary.write_bytes(b"fixture")
            tables = root / "tables"
            tables.mkdir()
            table = tables / "KQvK.rtbw"
            table.write_bytes(b"table-v1")
            original = analysis_configuration(binary, 10, tables)
            self.assertNotEqual(original, analysis_configuration(binary, 10))
            table.write_bytes(b"table-v2")
            self.assertNotEqual(original, analysis_configuration(binary, 10, tables))
            (tables / "KRvK.rtbw").write_bytes(b"second")
            self.assertEqual(len(analysis_configuration(binary, 10, tables)["syzygy_wdl"]), 2)

    def test_invalid_depth_and_missing_tables_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "sf"
            binary.write_bytes(b"fixture")
            for depth, syzygy in ((0, None), (10, root / "missing"), (10, root)):
                with self.subTest(depth=depth, syzygy=syzygy), self.assertRaises(ValueError):
                    analysis_configuration(binary, depth, syzygy)


class AnalysisResumeTests(unittest.TestCase):
    CONFIG = {"depth": 10, "stockfish_sha256": "fixture"}
    GAME = {"run_name": "r", "game_no": 1, "run_type": "AB"}

    def test_same_identity_resumes_without_rewriting_config(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            identity = prepare_output(out, self.CONFIG, workers=1)
            before = (out / "config.json").read_bytes()
            self.assertEqual(prepare_output(out, self.CONFIG, workers=3), identity)
            self.assertEqual((out / "config.json").read_bytes(), before)

    def test_different_identity_refuses_before_modifying_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            prepare_output(out, self.CONFIG)
            before = (out / "config.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "new --out"):
                prepare_output(out, {**self.CONFIG, "depth": 11})
            self.assertEqual((out / "config.json").read_bytes(), before)

    def test_legacy_output_remains_readable_but_cannot_be_resumed_as_new(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_cache(out, fake_game("r#1"))
            analysis.seal_part(out)
            self.assertEqual(analysis.processed_game_ids(out), {"r#1"})
            self.assertEqual(analysis.aggregate(out)["games"], 1)
            with self.assertRaisesRegex(ValueError, "new --out"):
                prepare_output(out, self.CONFIG)
            self.assertFalse((out / "config.json").exists())

    def test_legacy_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            path = out / "config.json"
            path.write_text('{"depth": 8}', encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare_output(out, self.CONFIG)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"depth": 8}')

    def test_cache_is_reused_only_with_its_identity_and_valid_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            identity = prepare_output(out, self.CONFIG)
            with patch.object(analysis, "analyze_game", return_value=fake_game("r#1")) as evaluate:
                cache = Path(analysis._analyze_task(self.GAME, str(out), 10))
                analysis._analyze_task(self.GAME, str(out), 10)
                self.assertEqual(evaluate.call_count, 1)
                payload = json.loads(cache.read_text(encoding="utf-8"))
                self.assertEqual(payload["analysis_fingerprint"], identity)
                payload["analysis_fingerprint"] = "another-configuration"
                cache.write_text(json.dumps(payload), encoding="utf-8")
                analysis._analyze_task(self.GAME, str(out), 10)
                self.assertEqual(evaluate.call_count, 2)
                cache.write_text("half-written {", encoding="utf-8")
                analysis._analyze_task(self.GAME, str(out), 10)
                self.assertEqual(evaluate.call_count, 3)
            self.assertFalse(cache.with_name(cache.name + ".tmp").exists())

    def test_task_depth_must_match_the_output_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            prepare_output(out, self.CONFIG)
            with patch.object(analysis, "analyze_game") as evaluate, self.assertRaises(ValueError):
                analysis._analyze_task(self.GAME, str(out), 11)
            evaluate.assert_not_called()

    def test_cache_and_part_names_depend_on_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a", Path(directory) / "b"
            x = prepare_output(a, self.CONFIG)
            y = prepare_output(b, {**self.CONFIG, "depth": 11})
            self.assertNotEqual(analysis.cache_path(a, self.GAME).name, analysis.cache_path(b, self.GAME).name)
            self.assertNotEqual(analysis.part_id(["r#1"], x), analysis.part_id(["r#1"], y))

    def test_matching_cache_seals_and_resumes_with_tagged_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            identity = prepare_output(out, self.CONFIG)
            game = {**fake_game("r#1"), "analysis_fingerprint": identity}
            write_cache(out, game)
            entry = analysis.seal_part(out)
            self.assertEqual(entry["analysis_fingerprint"], identity)
            self.assertEqual(analysis.processed_game_ids(out), {"r#1"})
            self.assertEqual(analysis.aggregate(out)["games"], 1)
            self.assertIsNone(analysis.seal_part(out))

    def test_foreign_or_untagged_cache_cannot_be_sealed(self):
        for identity in (None, "different"):
            with self.subTest(identity=identity), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                prepare_output(out, self.CONFIG)
                write_cache(out, {**fake_game("r#1"), "analysis_fingerprint": identity})
                with self.assertRaisesRegex(ValueError, "identity"):
                    analysis.seal_part(out)
                self.assertFalse((out / "parts.json").exists())

    def test_foreign_or_untagged_part_cannot_be_processed(self):
        for identity in (None, "different"):
            with self.subTest(identity=identity), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                expected = prepare_output(out, self.CONFIG)
                write_cache(out, {**fake_game("r#1"), "analysis_fingerprint": expected})
                analysis.seal_part(out)
                path = out / "parts.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest["parts"][0]["analysis_fingerprint"] = identity
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "identity"):
                    analysis.processed_game_ids(out)
                with self.assertRaisesRegex(ValueError, "identity"):
                    analyze_report.read_positions(out)

    def test_cli_mismatch_preserves_manifest_and_does_not_start_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            prepare_output(out, self.CONFIG)
            manifest = out / "manifest.json"
            manifest.write_text("original manifest", encoding="utf-8")
            binary = out / "sf"
            binary.write_bytes(b"fixture")
            with patch.object(analysis, "build_manifest", return_value=([], {})), \
                 patch.object(analysis.subprocess, "run"), \
                 patch.object(analysis, "_init_worker") as worker:
                result = analysis.main(["--out", str(out), "--stockfish", str(binary), "--depth", "11"])
            self.assertEqual(result, 1)
            worker.assert_not_called()
            self.assertEqual(manifest.read_text(encoding="utf-8"), "original manifest")

    def test_cli_reuses_matching_parts_without_analysing_games_again(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            binary = out / "sf"
            binary.write_bytes(b"fixture")
            identity = prepare_output(out, analysis_configuration(binary, 10))
            write_cache(out, {**fake_game("r#1"), "analysis_fingerprint": identity})
            analysis.seal_part(out)
            with patch.object(analysis, "build_manifest", return_value=([self.GAME], {})), \
                 patch.object(analysis.subprocess, "run"), \
                 patch.object(analysis, "_init_worker") as worker, \
                 patch.object(analysis, "analyze_game") as evaluate:
                result = analysis.main(["--out", str(out), "--stockfish", str(binary), "--workers", "1"])
            self.assertEqual(result, 2)
            worker.assert_not_called()
            evaluate.assert_not_called()
            self.assertEqual(analysis.processed_game_ids(out), {"r#1"})

    def test_configured_tablebase_failure_is_not_silently_ignored(self):
        with patch.object(analysis.chess.engine.SimpleEngine, "popen_uci") as launch, \
             patch.object(analysis.chess_syzygy, "open_tablebase", side_effect=OSError("unreadable tables")):
            with self.assertRaisesRegex(OSError, "unreadable"):
                analysis._init_worker("fixture", 10, "fixture-tables")
            launch.return_value.quit.assert_called_once()
            self.assertIsNone(analysis._engine)

    def test_pool_startup_failure_reaches_task_instead_of_restarting_workers(self):
        with patch.object(analysis, "_worker_error", None), \
             patch.object(analysis, "_init_worker", side_effect=OSError("fixture startup failed")), \
             patch.object(analysis, "_close_worker", side_effect=RuntimeError("broken quit")), \
             patch.object(analysis, "_analyze_task") as evaluate:
            analysis._init_pool_worker("fixture", 10, "tables")
            with self.assertRaisesRegex(RuntimeError, "fixture startup failed"):
                analysis._task_wrapper((self.GAME, "fixture", 10))
            evaluate.assert_not_called()

    def test_tampered_configuration_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            prepare_output(out, self.CONFIG)
            path = out / "config.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            config["analysis_configuration"]["depth"] = 99
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid analysis identity"):
                active_fingerprint(out)


if __name__ == "__main__":
    unittest.main()
