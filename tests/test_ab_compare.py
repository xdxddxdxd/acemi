"""A/B protocol, checkpoint and failure tests. Every match runner is mocked."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import ab_compare as ab, match
from tools.match_game import forfeit_result


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.new, self.old = self.root / "new", self.root / "old"
        self.new.mkdir()
        self.old.mkdir()
        (self.new / "openings").mkdir()
        original = ab.ROOT / "openings" / "acemi-64.txt"
        (self.new / "openings" / "acemi-64.txt").write_bytes(original.read_bytes())
        patches = [patch.object(ab, "ROOT", self.root),
                   patch.object(ab, "_runner_hashes", return_value={"fixture": "sha"}),
                   patch.object(ab, "_git", side_effect=lambda p, *a: "tree-new" if a[-1] == "HEAD:engine" else "collector"),
                   patch.object(ab, "source_info", side_effect=lambda p, sha: {
                       "path": str(Path(p).resolve()), "commit": sha,
                       "engine_tree": "tree-new" if sha == ab.NEW_COMMIT else "tree-old"})]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def plan(self, name="ab-fixture", **kwargs):
        return ab.prepare(self.root / "data" / "ab" / name, self.new, self.old, **kwargs)

    def fake_run(self, plan, chunk):
        run = self.root / "data" / "runs" / f"fixture_{plan['id']}_c{chunk['number']:02d}"
        run.mkdir(parents=True)
        meta = {"schema_version": 1, "git_commit": ab.NEW_COMMIT,
                "experiment": ab.experiment_meta(plan, chunk),
                "match_settings": {"games_requested": chunk["games"], "forfeit_policy": plan["forfeit_policy"]},
                "engine_settings": {"move_time_ms": plan["movetime_ms"], "hash_mb": plan["hash_mb"],
                                    "random_seed": chunk["seed"], "opening_book": False},
                "opponent": {"opening_book": False}}
        result = {"schema_version": 1, "games": chunk["games"], "wins": chunk["games"] // 2,
                  "draws": chunk["games"] // 2, "losses": 0, "aborted_games": 0,
                  "sprt": {"enabled": False}}
        for name in ab.ARTIFACTS:
            (run / name).write_text("fixture", encoding="utf-8")
        ab._write(run / "meta.json", meta)
        ab._write(run / "results.json", result)
        index = self.root / "data" / "index.csv"
        if not index.exists():
            index.write_text("run_name\n", encoding="utf-8")
        with index.open("a", encoding="utf-8") as stream:
            stream.write(run.name + "\n")
        return run

    def test_default_plan_is_100_games_50_distinct_openings_in_10_chunks(self):
        plan = self.plan()
        self.assertEqual(plan["games"], 100)
        self.assertEqual(len(plan["chunks"]), 10)
        self.assertEqual(sum(c["games"] for c in plan["chunks"]), 100)
        rows = [line for c in plan["chunks"]
                for line in (Path(plan["session_dir"]) / c["openings"]).read_text().splitlines()]
        self.assertEqual((len(rows), len(set(rows))), (50, 50))
        self.assertEqual(plan["sources"]["old"]["commit"], ab.OLD_COMMIT)
        self.assertEqual(plan["sources"]["new"]["commit"], ab.NEW_COMMIT)
        self.assertFalse(plan["opening_book"])
        self.assertFalse(plan["sprt_enabled"])

    def test_match_arguments_pin_cwds_timing_and_disjoint_seed_ranges(self):
        plan = self.plan()
        for c in plan["chunks"]:
            args = match._parse_args(ab.match_arguments(plan, c))
            self.assertEqual((args.games, args.movetime_ms, args.hash_mb), (10, 100, 16))
            self.assertEqual(args.engine_cwd, str(self.new))
            self.assertEqual(args.opponent_cwd, str(self.old))
            self.assertEqual(args.git_commit, ab.NEW_COMMIT)
            self.assertEqual(args.seed, 1 + (c["number"] - 1) * 10)
            self.assertEqual(args.engine_option, ["OwnBook=false"])
            self.assertEqual(args.opponent_option, ["OwnBook=false"])
            self.assertFalse(args.sprt)

    def test_500ms_bulk_plan_runs_all_100_games_in_one_match(self):
        plan = self.plan(name="ab-500ms", chunk_games=100, movetime_ms=500)
        self.assertEqual(len(plan["chunks"]), 1)
        chunk = plan["chunks"][0]
        args = match._parse_args(ab.match_arguments(plan, chunk))
        self.assertEqual((args.games, args.movetime_ms), (100, 500))
        self.assertEqual(chunk["global_game_start"], 1)
        rows = (Path(plan["session_dir"]) / chunk["openings"]).read_text().splitlines()
        self.assertEqual((len(rows), len(set(rows))), (50, 50))
        self.assertFalse(args.sprt)
        self.assertEqual(plan["id"], "ab-500ms")

    def test_completed_chunk_is_not_replayed_and_scores_are_new_perspective(self):
        plan = self.plan(games=4, chunk_games=2)
        def runner(argv, *, experiment):
            c = plan["chunks"][experiment["chunk"] - 1]
            self.fake_run(plan, c)
            return 0
        with patch.object(ab.match, "main", side_effect=runner) as run, contextlib.redirect_stdout(io.StringIO()):
            ab.run_chunk(plan, 1)
            ab.run_chunk(plan, 1)
            result = ab.run_chunk(plan, 2)
            self.assertEqual(run.call_count, 2)
        self.assertEqual((result["games"], result["wins"], result["draws"], result["losses"]), (4, 2, 2, 0))
        self.assertEqual(result["score_pct"], 75)
        self.assertEqual(result["status"], "completed")

    def test_completed_raw_run_is_adopted_after_lost_checkpoint(self):
        plan = self.plan(games=2, chunk_games=2)
        self.fake_run(plan, plan["chunks"][0])
        with patch.object(ab.match, "main") as run:
            result = ab.run_chunk(plan, 1)
            run.assert_not_called()
        self.assertEqual(result["recorded_attempts"], 2)

    def test_started_without_finalized_records_does_not_silently_replay(self):
        plan = self.plan(games=2, chunk_games=2)
        state = Path(plan["session_dir"]) / "chunks" / "chunk_01.started.json"
        ab._write(state, {"schema_version": 1})
        with patch.object(ab.match, "main") as run:
            with self.assertRaisesRegex(ValueError, "Stop the old Kaggle"):
                ab.run_chunk(plan, 1)
            run.assert_not_called()

    def test_runner_failure_preserves_logs_and_experiment_protocol(self):
        plan = self.plan(games=2, chunk_games=2)
        with patch.object(ab.match, "main", return_value=2):
            with self.assertRaises(RuntimeError):
                ab.run_chunk(plan, 1)
        out = Path(plan["session_dir"])
        self.assertTrue((out / "protocol.json").exists())
        self.assertTrue(list((out / "chunks").glob("*.log")))
        self.assertEqual(ab._read(out / "results.json")["status"], "in_progress")

    def test_completed_artifact_changes_are_rejected_without_replaying(self):
        plan = self.plan(games=2, chunk_games=2)
        chunk = plan["chunks"][0]
        run_dir = self.fake_run(plan, chunk)
        ab._record_checkpoint(plan, chunk, run_dir)
        (run_dir / "engine.log.gz").write_text("changed", encoding="utf-8")
        with patch.object(ab.match, "main") as runner:
            with self.assertRaisesRegex(ValueError, "must not be replayed"):
                ab.run_chunk(plan, 1)
            runner.assert_not_called()

    def test_protocol_opening_and_runner_identity_changes_are_rejected(self):
        plan = self.plan()
        out = Path(plan["session_dir"])
        self.assertEqual(ab.load_plan(out), plan)
        with patch.object(ab, "_runner_hashes", return_value={"changed": "sha"}):
            with self.assertRaisesRegex(ValueError, "runner code changed"):
                ab.load_plan(out)
        path = out / plan["chunks"][0]["openings"]
        path.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "opening file changed"):
            ab.load_plan(out)

    def test_invalid_count_and_existing_output_are_rejected(self):
        for counts in ((99, 10), (100, 3), (130, 10)):
            with self.assertRaises(ValueError):
                self.plan("invalid", games=counts[0], chunk_games=counts[1])
        self.plan()
        with self.assertRaises(FileExistsError):
            self.plan()

    def test_pc_cli_never_calls_match_runner(self):
        with patch.object(ab, "_on_kaggle", return_value=False), \
             patch.object(ab.match, "main") as run, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ab.main(["run", "--session", "fixture", "--chunk", "1"]), 2)
            run.assert_not_called()


class SourceAndForfeitTests(unittest.TestCase):
    def test_source_commit_and_dirty_checkout_are_rejected(self):
        with patch.object(ab, "_git", return_value="wrong-sha"):
            with self.assertRaisesRegex(ValueError, "commit mismatch"):
                ab.source_info(Path("fixture"), ab.NEW_COMMIT)
        with patch.object(ab, "_git", side_effect=[ab.NEW_COMMIT, " M engine/search.py"]):
            with self.assertRaisesRegex(ValueError, "dirty"):
                ab.source_info(Path("fixture"), ab.NEW_COMMIT)

    def test_both_builds_lose_on_forfeit_and_legacy_opponent_aborts_remain(self):
        for white in (True, False):
            new_loss = "0-1" if white else "1-0"
            old_loss = "1-0" if white else "0-1"
            self.assertEqual(forfeit_result("engine", white, symmetric=True), new_loss)
            self.assertEqual(forfeit_result("opponent", white, symmetric=True), old_loss)
            self.assertEqual(forfeit_result("engine", white), new_loss)
            self.assertEqual(forfeit_result("opponent", white), "*")

    def test_bad_experiment_identifier_fails_before_engines_start(self):
        with patch.object(match, "UciEngine") as engine:
            with self.assertRaises(ValueError):
                match.main([], experiment={"id": "../bad", "chunk": 1})
            engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
