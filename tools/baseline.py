"""Save a reproducible correctness and fixed-depth search reference.

Run this collector from the current checkout, pointing at a clean, pinned source
checkout when recording an older engine. Results are immutable, contain no Elo
claim, and remain available even when the tests or benchmark fail.

    python -m tools.baseline --source-root ../acemi-reference --depth 4
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = ("engine", "tools", "tests", "openings", "requirements-tools.txt")

# A separate process imports tests and engine from the source checkout, never
# from the collector's checkout. Read counts from unittest itself, not log text.
TEST_RUNNER = """
import json
import sys
import unittest
from pathlib import Path

suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
result = unittest.TextTestRunner(verbosity=2).run(suite)
document = {
    'schema_version': 1,
    'tests_run': result.testsRun,
    'successful': result.wasSuccessful() and result.testsRun > 0,
    'failures': [test.id() for test, _ in result.failures],
    'errors': [test.id() for test, _ in result.errors],
    'skipped': [{'test': test.id(), 'reason': reason} for test, reason in result.skipped],
    'expected_failures': [test.id() for test, _ in result.expectedFailures],
    'unexpected_successes': [test.id() for test in result.unexpectedSuccesses],
}
Path(sys.argv[1]).write_text(json.dumps(document, indent=2) + '\\n', encoding='utf-8')
sys.exit(0 if document['successful'] else 1)
"""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        text=True, encoding="utf-8",
    ).stdout.strip()


def _run_logged(command: list[str], source: Path, log: Path) -> int:
    print(f"Running {log.name}; full output: {log}", flush=True)
    with log.open("w", encoding="utf-8") as stream:
        return subprocess.run(
            command, cwd=source, stdout=stream, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace",
        ).returncode


def collect(
    source_root: Path,
    out_dir: Path | None = None,
    *,
    depth: int = 4,
    label: str = "reference",
    expected_commit: str | None = None,
) -> tuple[Path, dict]:
    """Record tests and a benchmark without changing the source checkout."""
    from tools.bench import compare

    source = source_root.resolve()
    if depth < 1:
        raise ValueError("Reference depth must be at least 1")
    for relative in ("engine/__init__.py", "tests", "tools/bench.py"):
        if not (source / relative).exists():
            raise ValueError(f"Source checkout is missing {relative}: {source}")
    commit = _git(source, "rev-parse", "HEAD")
    if expected_commit and commit != expected_commit:
        raise ValueError(f"Source commit mismatch: {commit} != {expected_commit}")
    dirty = _git(source, "status", "--porcelain", "--untracked-files=all", "--", *SOURCE_PATHS)
    if dirty:
        raise ValueError("Reference source has uncommitted code; use a clean, pinned checkout")

    destination = out_dir.resolve() if out_dir else ROOT / "data" / "baselines" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{commit[:7]}_{uuid.uuid4().hex[:8]}"
    )
    # Never overwrite an earlier measurement, even if it failed.
    destination.mkdir(parents=True, exist_ok=False)
    test_command = [sys.executable, "-c", TEST_RUNNER, str(destination / "tests.json")]
    bench_command = [
        sys.executable, "-m", "tools.bench", "--depth", str(depth),
        "--label", label, "--out", str(destination / "bench.json"),
    ]
    meta = {
        "schema_version": 1,
        "kind": "correctness_and_fixed_depth_reference",
        "label": label,
        "started_at": _utc(),
        "source": {
            "git_commit": commit,
            "git_tree": _git(source, "rev-parse", "HEAD^{tree}"),
            "engine_tree": _git(source, "rev-parse", "HEAD:engine"),
            "git_dirty": False,
        },
        "collector": {
            "git_commit": _git(ROOT, "rev-parse", "HEAD"),
            "git_dirty": bool(_git(ROOT, "status", "--porcelain", "--",
                                    "tools/baseline.py", "tools/bench.py")),
        },
        "environment": {
            "runtime": platform.python_implementation(),
            "runtime_version": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "dependencies": json.loads(subprocess.run(
                [sys.executable, "-c",
                 "import importlib.metadata as m,json; "
                 "d={x.metadata['Name'].lower():x.version for x in m.distributions()}; "
                 "print(json.dumps({k:d.get(k) for k in ('python-chess','chess','numpy')}))"],
                cwd=source, check=True, capture_output=True, text=True, encoding="utf-8",
            ).stdout),
        },
        "protocol": {
            "depth": depth,
            "time_limit": None,
            "options": "source defaults; fresh Searcher per position; opening book bypassed",
            "test_command": [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            "benchmark_command": bench_command,
        },
    }
    _write_json(destination / "meta.json", meta)
    test_code = _run_logged(test_command, source, destination / "tests.log")
    try:
        tests = json.loads((destination / "tests.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tests = {"schema_version": 1, "successful": False, "tests_run": None,
                 "error": "Test process did not produce a valid summary; inspect tests.log"}
    tests["returncode"] = test_code
    _write_json(destination / "tests.json", tests)
    benchmark = {"status": "skipped", "returncode": None}
    status = "tests_failed"
    if test_code == 0 and tests.get("successful") and tests.get("tests_run", 0) > 0:
        bench_code = _run_logged(bench_command, source, destination / "bench.log")
        benchmark = {"status": "failed", "returncode": bench_code}
        status = "benchmark_failed"
        if bench_code == 0:
            try:
                document = json.loads((destination / "bench.json").read_text(encoding="utf-8"))
                valid, _ = compare(document, document)
                if not valid or document["depth"] != depth or not document["positions"]:
                    raise ValueError("Benchmark protocol or position list is invalid")
                document.update(schema_version=1, git_commit=commit,
                                engine_tree=meta["source"]["engine_tree"])
                _write_json(destination / "bench.json", document)
                benchmark["status"] = "passed"
                status = "passed"
            except (OSError, ValueError, KeyError, TypeError) as error:
                benchmark["error"] = str(error)

    results = {
        "schema_version": 1,
        "status": status,
        "finished_at": _utc(),
        "tests": {"returncode": test_code, "tests_run": tests.get("tests_run"),
                  "successful": tests.get("successful", False)},
        "benchmark": benchmark,
    }
    _write_json(destination / "results.json", results)
    (destination / "SUMMARY.md").write_text(
        f"# Reference: {label}\n\n"
        f"- Source commit: `{commit}`\n"
        f"- Engine tree: `{meta['source']['engine_tree']}`\n"
        f"- Runtime: {platform.python_implementation()} {platform.python_version()}\n"
        f"- Tests: {tests.get('tests_run')} run; exit {test_code}\n"
        f"- Fixed-depth benchmark: depth {depth}, {benchmark['status']}\n"
        f"- Status: **{status}**\n\n"
        "Raw results and logs are retained for failures too. This is a correctness/search "
        "reference, not a playing-strength measurement. Compare scores, FENs, depths, "
        "nodes and moves; elapsed times from different machines are not a speedup claim.\n",
        encoding="utf-8",
    )
    print(f"Reference recorded: {destination}", flush=True)
    print(f"Reference status: {status}", flush=True)
    return destination, results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--label", default="reference")
    parser.add_argument("--expected-commit", help="require this exact full source commit SHA")
    args = parser.parse_args(argv)
    try:
        _, results = collect(args.source_root, args.out_dir, depth=args.depth,
                             label=args.label, expected_commit=args.expected_commit)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Reference setup failed: {error}", file=sys.stderr)
        return 2
    return 0 if results["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
