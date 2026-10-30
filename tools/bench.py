"""Fixed-depth search benchmark: speed, and proof that a change did not alter the search.

Every position is searched to the same depth with a fresh Searcher (empty
transposition table, default options, no time limit), so the result does not depend
on the clock: score, completed depth, node count and best move must be identical
for two builds that search the same way. Only the time may differ.

    python -m tools.bench --out data/bench/new_cpython.json
    python -m tools.bench --engine-root ../old_checkout --out data/bench/old_cpython.json
    python -m tools.bench --compare data/bench/old_cpython.json data/bench/new_cpython.json

``--engine-root`` benchmarks the ``engine`` package found in another directory (an
older commit). The tool itself uses only the standard library, so it also runs under
PyPy (``pypy3 -m tools.bench``).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DEPTH = 4
POSITIONS = (
    ("start", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
    ("italian", "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"),
    ("endgame_rooks", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"),
    ("promotions", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"),
    ("tactical", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"),
    ("open_middlegame", "r2q1rk1/ppp2ppp/2np1n2/2b1p3/2B1P1b1/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 8"),
    ("queen_endgame", "6k1/5ppp/8/8/8/8/5PPP/3Q2K1 w - - 0 1"),
    ("closed", "r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/R3KB1R w KQ - 0 9"),
    ("minor_endgame", "8/5pk1/6p1/3n4/3B4/6P1/5PK1/8 w - - 0 1"),
)


def _cpu_model() -> str | None:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def run_benchmark(depth: int, label: str) -> dict:
    """Search every benchmark position to ``depth`` and return the measurements."""
    from engine import __version__
    from engine.board import Board
    from engine.search import Searcher

    rows = []
    total_nodes = 0
    total_seconds = 0.0
    for name, fen in POSITIONS:
        board = Board(fen)
        searcher = Searcher()
        started = time.perf_counter()
        result = searcher.search(board, depth=depth)
        seconds = time.perf_counter() - started
        total_nodes += result.nodes
        total_seconds += seconds
        rows.append(
            {
                "name": name,
                "fen": fen,
                "score": result.score,
                "depth": result.depth,
                "nodes": result.nodes,
                "best_move": None if result.best_move is None else result.best_move.uci(),
                "seconds": round(seconds, 4),
            }
        )
    return {
        "label": label,
        "date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "engine_version": __version__,
        "depth": depth,
        "runtime": platform.python_implementation(),
        "runtime_version": platform.python_version(),
        "cpu_model": _cpu_model(),
        "total_nodes": total_nodes,
        "total_seconds": round(total_seconds, 3),
        "nodes_per_second": round(total_nodes / total_seconds) if total_seconds > 0 else None,
        "positions": rows,
    }


def compare(first: dict, second: dict) -> tuple[bool, list[str]]:
    """Compare two benchmark documents. Returns (identical search, report lines)."""
    lines: list[str] = []
    identical = True
    if first["depth"] != second["depth"]:
        return False, [f"Depths differ: {first['depth']} vs {second['depth']}; cannot compare."]
    second_rows = {row["name"]: row for row in second["positions"]}
    lines.append(
        f"{'position':<16}{'nodes A':>10}{'nodes B':>10}{'sec A':>9}{'sec B':>9}{'speedup':>9}  same"
    )
    for row in first["positions"]:
        other = second_rows.get(row["name"])
        if other is None:
            identical = False
            lines.append(f"{row['name']:<16} missing in B")
            continue
        same = all(row[key] == other[key] for key in ("score", "depth", "nodes", "best_move"))
        identical = identical and same
        speedup = row["seconds"] / other["seconds"] if other["seconds"] > 0 else float("inf")
        lines.append(
            f"{row['name']:<16}{row['nodes']:>10}{other['nodes']:>10}"
            f"{row['seconds']:>9.2f}{other['seconds']:>9.2f}{speedup:>8.2f}x  {'yes' if same else 'NO'}"
        )
        if not same:
            lines.append(
                f"    A: score {row['score']} depth {row['depth']} nodes {row['nodes']} move {row['best_move']}"
            )
            lines.append(
                f"    B: score {other['score']} depth {other['depth']} nodes {other['nodes']} move {other['best_move']}"
            )
    total_speedup = (
        first["total_seconds"] / second["total_seconds"] if second["total_seconds"] > 0 else float("inf")
    )
    lines.append(
        f"Total: A {first['nodes_per_second']} nps ({first['label']}, {first['runtime']}), "
        f"B {second['nodes_per_second']} nps ({second['label']}, {second['runtime']}); "
        f"B is {total_speedup:.2f}x faster at fixed depth."
    )
    lines.append(
        "Search identical (score, depth, nodes, best move on every position): "
        + ("YES" if identical else "NO - the two builds do not search the same way")
    )
    return identical, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--label", default=None, help="name stored in the output (default: the file name)")
    parser.add_argument("--out", default=None, help="write the measurements to this JSON file")
    parser.add_argument("--engine-root", default=None, help="directory that holds the engine package to benchmark")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"), help="compare two benchmark JSON files and exit")
    args = parser.parse_args(argv)

    if args.compare:
        first = json.loads(Path(args.compare[0]).read_text(encoding="utf-8"))
        second = json.loads(Path(args.compare[1]).read_text(encoding="utf-8"))
        identical, lines = compare(first, second)
        print("\n".join(lines))
        return 0 if identical else 1

    if args.engine_root:
        sys.path.insert(0, str(Path(args.engine_root).resolve()))
    label = args.label or (Path(args.out).stem if args.out else "benchmark")
    document = run_benchmark(args.depth, label)
    for row in document["positions"]:
        print(
            f"{row['name']:<16} depth {row['depth']} score {row['score']:>6} nodes {row['nodes']:>8} "
            f"move {row['best_move']} {row['seconds']:.2f}s"
        )
    print(
        f"Total: {document['total_nodes']} nodes in {document['total_seconds']:.2f}s = "
        f"{document['nodes_per_second']} nps ({document['runtime']} {document['runtime_version']}, "
        f"engine {document['engine_version']})"
    )
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
