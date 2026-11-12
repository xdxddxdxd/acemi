"""Kaggle-only correctness/cost gates for the opt-in RootMateGuard candidate."""

import argparse
import copy
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback

REFERENCE_COMMIT = "38b0722b084552d8e94eb62e3558d447b641969c"
CRITICAL_FEN = "rnb2rk1/ppp2ppp/8/1N1p4/1b1PnB1q/P7/1P1NPPPP/R2QKB1R w KQ - 1 10"
COMMON_OPTIONS = {"TTTwoContexts": True, "EvalPackedBase": True,
                  "QuiescenceSEE": False, "NextIterationPct": 150}
FEATURE_OPTIONS = {"new": {**COMMON_OPTIONS, "RootMateGuard": True},
                   "old": {**COMMON_OPTIONS, "RootMateGuard": False}}


def allows_mate(board):
    """Independent python-chess terminal oracle, used only by diagnostic workers."""
    if board.outcome(claim_draw=True) is not None:
        return False
    for reply in list(board.legal_moves):
        board.push(reply)
        try:
            if board.is_checkmate():
                return True
        finally:
            board.pop()
    return False


def worker(source, out, enabled):
    source = Path(source).resolve()
    sys.path.insert(0, str(source))
    import chess
    import engine
    from tools import ab_compare as ab
    from engine.board import Board
    from engine.eval.classic import EvalFlags
    from engine.search import Searcher
    from tools.bench import POSITIONS
    if Path(engine.__file__).resolve().parents[1] != source:
        raise ValueError("Worker imported a different engine")

    def run(fen, movetime_ms=None):
        board = Board(fen)
        before = copy.deepcopy(board.__dict__)
        flags = EvalFlags()
        flags.packed_base = True
        options = {"root_mate_guard": True} if enabled else {}
        searcher = Searcher(eval_flags=flags, tt_two_contexts=True, **options)
        start = time.perf_counter()
        result = searcher.search(board, depth=3 if movetime_ms is None else 64,
                                 movetime_ms=movetime_ms)
        elapsed = time.perf_counter() - start
        if board.__dict__ != before:
            raise ValueError("Search did not restore the complete board state")
        row = dict(fen=fen, best_move=result.best_move.uci() if result.best_move else None,
                   score=result.score, mate=result.mate, depth=result.depth,
                   attempted_depth=result.attempted_depth, nodes=result.nodes,
                   seconds=elapsed, search_time_ms=result.time_ms,
                   root_guard=searcher.root_guard_stats if enabled else {})
        if movetime_ms is not None:
            oracle = chess.Board(fen)
            if not row["best_move"]:
                raise ValueError("Critical position returned no move")
            oracle.push_uci(row["best_move"])
            row.update(movetime_ms=movetime_ms, allows_mate_in_one=allows_mate(oracle))
        return row

    rows = [dict(name=name, **run(fen)) for name, fen in POSITIONS]
    critical = [run(CRITICAL_FEN, ms) for ms in (100, 500)]
    ab._write(out, dict(schema_version=1, source_commit=ab._git(source, "rev-parse", "HEAD"),
                        engine_tree=ab._git(source, "rev-parse", "HEAD:engine"),
                        root_mate_guard=enabled, positions=rows, critical=critical,
                        total_seconds=sum(row["seconds"] for row in rows)))


def signature(document):
    return [(row["name"], row["fen"], row["best_move"], row["score"], row["mate"],
             row["depth"], row["attempted_depth"], row["nodes"])
            for row in document["positions"]]


def decision(reference, controls, candidates):
    """Cost and tactical eligibility only; never declares a strength gain."""
    if len(controls) != 3 or len(candidates) != 3:
        raise ValueError("Require three alternating measurements per policy")
    if any(signature(row) != signature(reference) for row in controls):
        raise ValueError("Guard-off search differs from pinned current-main reference")
    for enabled, documents in ((False, controls), (True, candidates)):
        for document in documents:
            if document["root_mate_guard"] is not enabled:
                raise ValueError("Diagnostic policy label differs")
            if not 0 < document["total_seconds"] < float("inf"):
                raise ValueError("Invalid elapsed seconds")
            if [(row["name"], row["fen"]) for row in document["positions"]] != [
                    (row["name"], row["fen"]) for row in reference["positions"]]:
                raise ValueError("Position sets differ")
            if [row["movetime_ms"] for row in document["critical"]] != [100, 500]:
                raise ValueError("Critical diagnostics must include 100 and 500 ms")
    control = statistics.median(row["total_seconds"] for row in controls)
    candidate = statistics.median(row["total_seconds"] for row in candidates)
    tactical_passed = all(row["allows_mate_in_one"] is False
                          for doc in candidates for row in doc["critical"])
    reasons = []
    if not tactical_passed:
        reasons.append("Candidate still permits mate in one in a critical diagnostic")
    if candidate > control * 1.1:
        reasons.append("Fixed-depth median cost is over 10% above control")
    return dict(eligible_to_run_match=not reasons, reasons=reasons,
                control_median_seconds=control, candidate_median_seconds=candidate,
                elapsed_change_pct=(candidate / control - 1) * 100,
                critical_tactical_passed=tactical_passed,
                note="Diagnostic/cost gate only; playing strength requires the paired A/B result")


def command(args, cwd, log):
    with Path(log).open("x", encoding="utf-8") as stream:
        result = subprocess.run(args, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Preflight failed; inspect {log}")


def validate(session, reference):
    from tools import ab_compare as ab
    plan = ab.load_plan(session)
    if (plan["feature_options"] != FEATURE_OPTIONS
            or plan["sources"]["new"]["commit"] != plan["sources"]["old"]["commit"]):
        raise ValueError("Isolate RootMateGuard on/off on the same source commit")
    source = Path(plan["sources"]["new"]["path"]).resolve()
    reference = Path(reference).resolve()
    for checkout, expected in ((source, plan["sources"]["new"]["commit"]), (reference, REFERENCE_COMMIT)):
        if ab._git(checkout, "rev-parse", "HEAD") != expected:
            raise ValueError("Source commit differs")
        if ab._git(checkout, "status", "--porcelain", "--untracked-files=all", "--", "engine", "tests", "tools"):
            raise ValueError("Validation source is dirty")
    out = Path(session) / "validation"
    out.mkdir(exist_ok=True)
    status_path = out / "status.json"
    gate_path = Path(session) / "eligibility.json"
    identity = dict(experiment="root-mate-guard", protocol_sha256=plan["protocol_sha256"],
                    reference_commit=REFERENCE_COMMIT, validator_sha256=ab._sha(Path(__file__)))
    if status_path.exists():
        status = ab._read(status_path)
        if status.get("identity") != identity or not status.get("passed"):
            raise ValueError("Preflight changed/failed/interrupted; inspect logs and use a new session id")
        for name, digest in status["artifacts"].items():
            if ab._sha(out / name) != digest:
                raise ValueError("Saved validation artifact changed")
        gate = ab._read(gate_path)
        expected = decision(ab._read(out / "reference.json"),
                            [ab._read(out / f"bench-{i}-off.json") for i in (1, 2, 3)],
                            [ab._read(out / f"bench-{i}-on.json") for i in (1, 2, 3)])
        if gate != dict(schema_version=1, identity=identity, **expected):
            raise ValueError("Saved gate changed")
        print("Verified completed preflight; no searches repeated.", flush=True)
        return gate
    ab._write(status_path, dict(schema_version=1, identity=identity, passed=False, state="started"))
    try:
        print("Kaggle: full correctness suite, then alternating on/off diagnostics.", flush=True)
        command([sys.executable, "-u", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"],
                source, out / "tests.log")
        tasks = [("reference", reference, False)]
        for i in (1, 2, 3):
            tasks += [(f"bench-{i}-{label}", source, label == "on")
                      for label in (("off", "on") if i % 2 else ("on", "off"))]
        for label, checkout, enabled in tasks:
            print("Kaggle diagnostic:", label, flush=True)
            command([sys.executable, "-u", str(Path(__file__).resolve()), "--worker",
                     "--source", str(checkout), "--out", str(out / (label + ".json")),
                     *(["--guard"] if enabled else [])], source, out / (label + ".log"))
        gate = dict(schema_version=1, identity=identity,
                    **decision(ab._read(out / "reference.json"),
                               [ab._read(out / f"bench-{i}-off.json") for i in (1, 2, 3)],
                               [ab._read(out / f"bench-{i}-on.json") for i in (1, 2, 3)]))
        artifacts = {p.name: ab._sha(p) for p in out.iterdir() if p.is_file() and p != status_path}
        ab._write(status_path, dict(schema_version=1, identity=identity, passed=True,
                                   state="completed", artifacts=artifacts))
        ab._write(gate_path, gate)
        print(json.dumps(gate, indent=2), flush=True)
        return gate
    except Exception as error:
        ab._write(status_path, dict(schema_version=1, identity=identity, passed=False,
                                   state="failed", error=str(error)))
        (out / "preflight_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--guard", action="store_true")
    parser.add_argument("--session", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args(argv)
    if not Path("/kaggle/working").is_dir():
        parser.error("Full diagnostics and matches run only in Kaggle")
    if args.worker:
        if args.source is None or args.out is None:
            parser.error("Worker needs --source and --out")
        worker(args.source, args.out, args.guard)
    else:
        if args.session is None or args.reference is None:
            parser.error("Need --session and --reference")
        validate(args.session, args.reference)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
