"""Pure gate/CLI fixtures; no engine process, benchmark or match is launched."""

import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.root_mate_guard_experiment import decision, main


def fixture(enabled=False, seconds=10.0):
    return dict(root_mate_guard=enabled, total_seconds=seconds,
                positions=[dict(name="fixture", fen="fixture-fen", best_move="e2e4", score=7,
                                mate=None, depth=3, attempted_depth=3, nodes=123)],
                critical=[dict(movetime_ms=ms, allows_mate_in_one=False) for ms in (100, 500)])


class RootGuardGateTests(unittest.TestCase):
    def test_tactical_pass_and_affordable_cost_allow_only_a_match(self):
        result = decision(fixture(), [fixture() for _ in range(3)],
                          [fixture(True, sec) for sec in (10.1, 10.2, 10.3)])
        self.assertTrue(result["eligible_to_run_match"])
        self.assertAlmostEqual(result["elapsed_change_pct"], 2)
        self.assertIn("strength", result["note"])

    def test_expensive_candidate_is_skipped(self):
        result = decision(fixture(), [fixture() for _ in range(3)],
                          [fixture(True, 12) for _ in range(3)])
        self.assertFalse(result["eligible_to_run_match"])
        self.assertIn("10%", result["reasons"][0])

    def test_one_remaining_mating_blunder_blocks_matches(self):
        candidates = [fixture(True) for _ in range(3)]
        candidates[1]["critical"][0]["allows_mate_in_one"] = True
        result = decision(fixture(), [fixture() for _ in range(3)], candidates)
        self.assertFalse(result["eligible_to_run_match"])
        self.assertFalse(result["critical_tactical_passed"])

    def test_disabled_search_must_match_main_including_nodes(self):
        control = fixture()
        control["positions"][0]["nodes"] += 1
        with self.assertRaisesRegex(ValueError, "reference"):
            decision(fixture(), [control] * 3, [fixture(True)] * 3)

    def test_missing_repeats_and_wrong_policies_are_rejected(self):
        with self.assertRaises(ValueError):
            decision(fixture(), [fixture()] * 2, [fixture(True)] * 3)
        with self.assertRaisesRegex(ValueError, "policy"):
            decision(fixture(), [fixture()] * 3, [fixture()] * 3)

    def test_position_or_time_settings_cannot_be_mixed(self):
        for change in (lambda d: d["positions"][0].update(fen="foreign"),
                       lambda d: d["critical"][0].update(movetime_ms=50)):
            candidates = [fixture(True) for _ in range(3)]
            change(candidates[0])
            with self.assertRaises(ValueError):
                decision(fixture(), [fixture()] * 3, candidates)

    def test_nonfinite_measurement_is_rejected(self):
        for seconds in (0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                decision(fixture(), [fixture()] * 3, [fixture(True, seconds)] * 3)

    def test_pc_guard_blocks_both_workers_and_full_validation(self):
        from unittest.mock import patch
        with patch("pathlib.Path.is_dir", return_value=False), contextlib.redirect_stderr(io.StringIO()):
            for argv in (["--session", "fixture", "--reference", "fixture"],
                         ["--worker", "--source", "fixture", "--out", "fixture"]):
                with self.assertRaises(SystemExit) as error:
                    main(argv)
                self.assertEqual(error.exception.code, 2)

    def test_worker_imports_target_source_in_a_fresh_process(self):
        # A fake reference cannot run a real search. This catches accidentally
        # importing the collector's engine before selecting the reference root.
        import json
        import tools.root_mate_guard_experiment as experiment
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                "engine/__init__.py": "",
                "engine/board.py": "class Board:\n def __init__(self,fen): self.fen=fen\n",
                "engine/eval/__init__.py": "",
                "engine/eval/classic.py": "class EvalFlags: pass\n",
                "engine/search.py": "from types import SimpleNamespace as N\nclass Searcher:\n"
                                    " def __init__(self,**kw): pass\n"
                                    " def search(self,*a,**kw): return N(best_move=N(uci=lambda:'f4g3'),"
                                    "score=7,mate=None,depth=3,attempted_depth=3,nodes=1,time_ms=0)\n",
                "tools/__init__.py": "",
                "tools/bench.py": f"POSITIONS=[('fake-reference',{experiment.CRITICAL_FEN!r})]\n",
                "tools/ab_compare.py": "import json\nfrom pathlib import Path\n"
                                        "def _git(*args): return 'fake-reference'\n"
                                        "def _write(p,v): Path(p).write_text(json.dumps(v))\n",
            }
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            out = root / "worker.json"
            script = ("import runpy,sys; m=runpy.run_path(sys.argv[1],run_name='fixture_worker');"
                      "m['worker'](sys.argv[2],sys.argv[3],False)")
            result = subprocess.run([sys.executable, "-c", script, experiment.__file__, str(root), str(out)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            document = json.loads(out.read_text())
            self.assertEqual(document["source_commit"], "fake-reference")
            self.assertEqual(document["positions"][0]["name"], "fake-reference")

