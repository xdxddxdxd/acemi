"""Reference recording must preserve provenance and failures, never old results."""

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import baseline, bench


def benchmark_document():
    return {
        "label": "fixture", "depth": 2, "runtime": "CPython", "runtime_version": "3.12.0",
        "cpu_model": "test CPU", "total_seconds": 1.0, "nodes_per_second": 10,
        "positions": [{"name": "start", "fen": "fixture FEN", "score": 0,
                       "depth": 2, "nodes": 10, "best_move": "e2e4", "seconds": 1.0}],
    }


class BenchmarkComparisonTests(unittest.TestCase):
    def test_same_names_do_not_hide_different_positions(self):
        original = benchmark_document()
        changed = copy.deepcopy(original)
        changed["positions"][0]["fen"] = "different FEN"
        same, lines = bench.compare(original, changed)
        self.assertFalse(same)
        self.assertTrue(any("FEN differs" in line for line in lines))

    def test_extra_and_duplicate_positions_are_rejected(self):
        original = benchmark_document()
        extra = copy.deepcopy(original)
        extra["positions"].append({**extra["positions"][0], "name": "extra"})
        self.assertFalse(bench.compare(original, extra)[0])
        duplicate = copy.deepcopy(original)
        duplicate["positions"].append(dict(duplicate["positions"][0]))
        self.assertFalse(bench.compare(original, duplicate)[0])

    def test_empty_and_missing_positions_are_rejected(self):
        original = benchmark_document()
        empty = copy.deepcopy(original)
        empty["positions"] = []
        self.assertFalse(bench.compare(original, empty)[0])
        self.assertFalse(bench.compare(empty, empty)[0])

    def test_different_hardware_does_not_claim_a_speedup(self):
        original = benchmark_document()
        other = copy.deepcopy(original)
        other.update(cpu_model="different CPU", total_seconds=0.5)
        same, lines = bench.compare(original, other)
        self.assertTrue(same)
        self.assertIn("not an isolated speedup", "\n".join(lines))
        self.assertNotIn("faster at fixed depth", "\n".join(lines))


class ReferenceRecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        for directory in ("engine", "tools", "tests"):
            folder = self.source / directory
            folder.mkdir(parents=True)
            (folder / "__init__.py").write_text("", encoding="utf-8")
        # Each fixture runs real unittest and a separate benchmark process. No
        # production engine search is needed to test recording failure paths.
        (self.source / "tests" / "test_fixture.py").write_text(
            "import unittest\nclass Fixture(unittest.TestCase):\n"
            "    def test_reference(self): self.assertTrue(True)\n", encoding="utf-8",
        )
        document = json.dumps(benchmark_document())
        (self.source / "tools" / "bench.py").write_text(
            "import json,sys\nfrom pathlib import Path\n"
            f"document = json.loads({document!r})\n"
            "Path(sys.argv[sys.argv.index('--out')+1]).write_text(json.dumps(document), encoding='utf-8')\n",
            encoding="utf-8",
        )
        self.git("init", "-q")
        self.commit()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.source), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Reference test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        self.sha = self.git("rev-parse", "HEAD")

    def test_clean_pinned_source_produces_complete_reference(self):
        destination, results = baseline.collect(self.source, self.root / "record", depth=2,
                                                expected_commit=self.sha)
        self.assertEqual(results["status"], "passed")
        self.assertEqual(results["tests"]["tests_run"], 1)
        meta = json.loads((destination / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["source"]["git_commit"], self.sha)
        document = json.loads((destination / "bench.json").read_text(encoding="utf-8"))
        self.assertEqual(document["git_commit"], self.sha)
        for name in ("tests.log", "bench.log", "tests.json", "results.json", "SUMMARY.md"):
            self.assertTrue((destination / name).exists(), name)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_failed_tests_are_saved_and_benchmark_is_skipped(self):
        test_file = self.source / "tests" / "test_fixture.py"
        test_file.write_text(test_file.read_text().replace("assertTrue(True)", "assertTrue(False)"))
        self.commit()
        destination, results = baseline.collect(self.source, self.root / "failure", depth=2)
        self.assertEqual(results["status"], "tests_failed")
        tests = json.loads((destination / "tests.json").read_text())
        self.assertEqual(len(tests["failures"]), 1)
        self.assertFalse((destination / "bench.json").exists())
        self.assertIn("AssertionError", (destination / "tests.log").read_text())
        self.assertTrue((destination / "SUMMARY.md").exists())

    def test_failed_benchmark_is_saved_without_passing_reference(self):
        (self.source / "tools" / "bench.py").write_text("raise SystemExit(3)\n")
        self.commit()
        destination, results = baseline.collect(self.source, self.root / "bench-failure", depth=2)
        self.assertEqual(results["status"], "benchmark_failed")
        self.assertEqual(results["benchmark"]["returncode"], 3)
        self.assertTrue((destination / "results.json").exists())

    def test_empty_test_suite_cannot_be_a_passing_reference(self):
        (self.source / "tests" / "test_fixture.py").write_text("# No tests\n")
        self.commit()
        _, results = baseline.collect(self.source, self.root / "empty-suite", depth=2)
        self.assertEqual(results["status"], "tests_failed")
        self.assertEqual(results["tests"]["tests_run"], 0)

    def test_successful_process_with_invalid_benchmark_is_rejected(self):
        (self.source / "tools" / "bench.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "Path(sys.argv[sys.argv.index('--out')+1]).write_text('{}')\n"
        )
        self.commit()
        _, results = baseline.collect(self.source, self.root / "invalid-bench", depth=2)
        self.assertEqual(results["status"], "benchmark_failed")
        self.assertIn("error", results["benchmark"])

    def test_existing_reference_is_never_overwritten(self):
        destination = self.root / "existing"
        destination.mkdir()
        marker = destination / "meta.json"
        marker.write_text("original")
        with self.assertRaises(FileExistsError):
            baseline.collect(self.source, destination, depth=2)
        self.assertEqual(marker.read_text(), "original")

    def test_dirty_or_wrong_source_commit_is_rejected_before_writing(self):
        destination = self.root / "rejected"
        with self.assertRaisesRegex(ValueError, "commit mismatch"):
            baseline.collect(self.source, destination, expected_commit="0" * 40)
        (self.source / "engine" / "__init__.py").write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "uncommitted code"):
            baseline.collect(self.source, destination)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
