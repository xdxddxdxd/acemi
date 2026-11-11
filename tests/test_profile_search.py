"""Profiling reports use fixtures; no production search is run here."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import profile_search
from tests.test_baseline import benchmark_document


class ProfileReportTests(unittest.TestCase):
    def test_engine_rows_normalize_paths_and_keep_call_counts(self):
        root = Path(tempfile.gettempdir()) / "profile-fixture"
        stats = {
            (str(root / "engine" / "movegen.py"), 20, "generate_legal_moves"): (2, 5, .1, .3, {}),
            (str(root / "engine" / "search.py"), 10, "_quiesce"): (1, 9, .2, .5, {}),
            (str(root / "tools" / "bench.py"), 1, "run_benchmark"): (1, 1, .1, .7, {}),
        }
        rows = profile_search.engine_rows(stats, root)
        self.assertEqual([row["function"] for row in rows], ["_quiesce", "generate_legal_moves"])
        self.assertEqual(rows[1]["file"], "engine/movegen.py")
        self.assertEqual((rows[1]["primitive_calls"], rows[1]["total_calls"]), (2, 5))

    def test_profile_comparison_ignores_timing_but_detects_changed_search(self):
        first = {"benchmark": benchmark_document(), "functions": [
            {"file": "engine/movegen.py", "function": "_pinned_squares", "total_calls": 20}]}
        second = copy.deepcopy(first)
        second["benchmark"]["total_seconds"] = .1
        second["functions"][0]["total_calls"] = 10
        same, lines = profile_search.compare_profiles(first, second)
        self.assertTrue(same)
        self.assertIn("A 20 calls; B 10 calls", "\n".join(lines))
        self.assertNotIn("speedup", "\n".join(lines))
        second["benchmark"]["positions"][0]["nodes"] += 1
        self.assertFalse(profile_search.compare_profiles(first, second)[0])

    def test_empty_duplicate_and_different_depth_profiles_are_not_equal(self):
        first = {"benchmark": benchmark_document(), "functions": []}
        for rows in ([], first["benchmark"]["positions"] * 2):
            changed = copy.deepcopy(first)
            changed["benchmark"]["positions"] = rows
            with self.assertRaises(ValueError):
                profile_search.compare_profiles(first, changed)
        changed = copy.deepcopy(first)
        changed["benchmark"]["depth"] += 1
        self.assertFalse(profile_search.compare_profiles(first, changed)[0])

    def test_existing_output_and_wrong_tree_are_rejected_before_benchmarking(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "profile.json"
            out.write_text("preserve", encoding="utf-8")
            with patch.object(profile_search, "run_benchmark") as run:
                with self.assertRaises(FileExistsError):
                    profile_search.capture(profile_search.ROOT, out, 3, "fixture")
                with patch.object(profile_search, "_git", return_value="different-tree"):
                    with self.assertRaisesRegex(ValueError, "tree differs"):
                        profile_search.capture(profile_search.ROOT, out.with_name("other.json"),
                                               3, "fixture", "expected-tree")
                run.assert_not_called()
            self.assertEqual(out.read_text(encoding="utf-8"), "preserve")

    def test_capture_serializes_fixture_and_source_identity_without_searching(self):
        def git(source, *args):
            return "" if args[0] == "status" else "fixture-sha"
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "profile.json"
            original_path = sys.path[:]
            with patch.object(profile_search, "_git", side_effect=git), \
                 patch.object(profile_search, "run_benchmark", return_value=benchmark_document()) as run:
                document = profile_search.capture(profile_search.ROOT, out, 2, "fixture", "fixture-sha")
            run.assert_called_once_with(2, "fixture")
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved, document)
            self.assertEqual(saved["engine_tree"], "fixture-sha")
            self.assertEqual(saved["kind"], "instrumented_search_profile")
            self.assertIn("overhead", saved["note"])
            self.assertEqual(sys.path, original_path)

    def test_wrong_imported_engine_is_rejected_and_import_path_restored(self):
        def git(source, *args):
            return "" if args[0] == "status" else "fixture-sha"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_path = sys.path[:]
            with patch.object(profile_search, "_git", side_effect=git), \
                 patch.object(profile_search, "run_benchmark") as run:
                with self.assertRaisesRegex(ValueError, "Wrong engine"):
                    profile_search.capture(root, root / "profile.json", 3, "fixture")
                run.assert_not_called()
            self.assertEqual(sys.path, original_path)
            self.assertFalse((root / "profile.json").exists())


if __name__ == "__main__":
    unittest.main()
