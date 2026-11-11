"""Kaggle-only search diagnostics. Instrumented times are not speed measurements.

The current tool can profile a pinned older engine via --engine-root. Use the
ordinary, uninstrumented baseline benchmark to compare actual elapsed times.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import subprocess
import sys
from pathlib import Path

from tools.bench import run_benchmark

ROOT = Path(__file__).resolve().parents[1]


def engine_rows(stats: dict, source: Path) -> list[dict]:
    rows = []
    for (filename, line, function), (primitive, calls, own, cumulative, _) in stats.items():
        try:
            relative = Path(filename).resolve().relative_to(source.resolve())
        except ValueError:
            continue
        if not relative.parts or relative.parts[0] != "engine":
            continue
        rows.append({"file": relative.as_posix(), "line": line, "function": function,
                     "primitive_calls": primitive, "total_calls": calls,
                     "self_seconds": own, "cumulative_seconds": cumulative})
    return sorted(rows, key=lambda row: (-row["cumulative_seconds"], row["file"], row["line"]))


def _git(source: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(source), *args], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def capture(source: Path, out: Path, depth: int, label: str,
            expected_engine_tree: str | None = None) -> dict:
    if out.exists():
        raise FileExistsError(f"Profile output already exists: {out}")
    if depth < 1:
        raise ValueError("Profile depth must be positive")
    source = source.resolve()
    tree = _git(source, "rev-parse", "HEAD:engine")
    if expected_engine_tree and tree != expected_engine_tree:
        raise ValueError("Profile engine tree differs from the collected benchmark")
    if _git(source, "status", "--porcelain", "--untracked-files=all", "--", "engine"):
        raise ValueError("Profile source engine is dirty")
    original_path = sys.path[:]
    try:
        sys.path.insert(0, str(source))
        import engine
        if Path(engine.__file__).resolve() != source / "engine" / "__init__.py":
            raise ValueError("Wrong engine already imported; run the profiler in a fresh Python process")
        profiler = cProfile.Profile()
        benchmark = profiler.runcall(run_benchmark, depth, label)
        document = {
            "schema_version": 1, "kind": "instrumented_search_profile",
            "source_commit": _git(source, "rev-parse", "HEAD"), "engine_tree": tree,
            "collector_commit": _git(ROOT, "rev-parse", "HEAD"),
            "note": "cProfile adds overhead; use the separate uninstrumented benchmark for speed comparisons",
            "benchmark": benchmark,
            "functions": engine_rows(pstats.Stats(profiler).stats, source),
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2)
            stream.write("\n")
        return document
    finally:
        sys.path[:] = original_path


def compare_profiles(first: dict, second: dict) -> tuple[bool, list[str]]:
    """Compare search outputs and function calls; never compare instrumented speed."""
    a, b = first["benchmark"], second["benchmark"]
    fields = ("name", "fen", "score", "depth", "nodes", "best_move")
    def signature(document):
        rows = document["positions"]
        if not rows or len({row["name"] for row in rows}) != len(rows):
            raise ValueError("Profile positions must be nonempty and unique")
        return sorted(tuple(row[field] for field in fields) for row in rows)
    identical = a["depth"] == b["depth"] and signature(a) == signature(b)
    lines = [f"Instrumented search identical: {identical}",
             "Function calls below are diagnostic; use uninstrumented bench.json for elapsed-time ratios."]
    def calls(document):
        counts = {}
        for row in document["functions"]:
            key = (row["file"], row["function"])
            counts[key] = counts.get(key, 0) + row["total_calls"]
        return counts
    ac, bc = calls(first), calls(second)
    for file, function in sorted(set(ac) | set(bc)):
        lines.append(f"{file}:{function}: A {ac.get((file, function), 0)} calls; B {bc.get((file, function), 0)} calls")
    return identical, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--label", default="profile")
    parser.add_argument("--expected-engine-tree")
    parser.add_argument("--compare", nargs=2, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.compare:
            docs = [json.loads(path.read_text(encoding="utf-8")) for path in args.compare]
            identical, lines = compare_profiles(*docs)
            print("\n".join(lines))
            return 0 if identical else 1
        if args.out is None:
            parser.error("--out is required when recording a profile")
        document = capture(args.engine_root, args.out, args.depth, args.label, args.expected_engine_tree)
        print(f"Profile recorded: {args.out}; engine {document['engine_tree']}")
        print("Top cumulative engine functions (instrumented seconds, not speed measurements):")
        for row in document["functions"][:20]:
            print(f"{row['file']}:{row['function']}: {row['total_calls']} calls, {row['cumulative_seconds']:.4f}s")
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Profile failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
