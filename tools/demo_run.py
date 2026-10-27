"""Create a clearly labeled synthetic run to smoke-test the data pipeline."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
INDEX_FIELDS = [
    "run_name",
    "date",
    "engine_version",
    "opponent",
    "games",
    "score_pct",
    "elo_diff",
    "sprt_decision",
]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_index(row: dict[str, object]) -> None:
    index_path = ROOT / "data" / "index.csv"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, str]] = []
    if index_path.exists():
        with index_path.open(newline="", encoding="utf-8") as stream:
            existing = list(csv.DictReader(stream))
    if any(item.get("run_name") == row["run_name"] for item in existing):
        return
    with index_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(existing)
        writer.writerow(row)


def create_demo_run(run_date: str | None = None) -> Path:
    now = datetime.now(timezone.utc)
    date_key = run_date or now.strftime("%Y%m%dT%H%M%SZ")
    run_name = f"{date_key}_0.1.0_demo_fake-{hashlib.sha1(date_key.encode()).hexdigest()[:7]}"
    run_dir = ROOT / "data" / "runs" / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    started = now.isoformat().replace("+00:00", "Z")
    meta = {
        "schema_version": SCHEMA_VERSION,
        "run_name": run_name,
        "is_demo": True,
        "date": date_key,
        "engine_version": "0.1.0",
        "git_commit": "synthetic-demo",
        "engine_settings": {
            "move_time_ms": 1000,
            "hash_mb": 16,
            "random_seed": 1,
            "opening_book": False,
        },
        "opponent": {"name": "Synthetic demo opponent", "version": "n/a", "uci_elo": None},
        "opening_set": "synthetic-demo",
        "hardware": {
            "cpu_count": os.cpu_count(),
            "ram_mb": None,
            "runtime": platform.python_implementation(),
            "runtime_version": platform.python_version(),
        },
        "started_at": started,
        "finished_at": started,
    }
    write_json(run_dir / "meta.json", meta)

    results = {
        "schema_version": SCHEMA_VERSION,
        "is_demo": True,
        "games": 1,
        "wins": 1,
        "draws": 0,
        "losses": 0,
        "score_pct": 100.0,
        "elo_diff": None,
        "elo_confidence_interval": None,
        "sprt": {
            "elo0": 0,
            "elo1": 10,
            "alpha": 0.05,
            "beta": 0.05,
            "llr": None,
            "decision": "demo_only",
        },
        "by_color": {
            "white": {"wins": 1, "draws": 0, "losses": 0},
            "black": {"wins": 0, "draws": 0, "losses": 0},
        },
        "tactics": None,
        "timeouts": 0,
        "illegal_moves": 0,
        "engine_crashes": 0,
        "average_plies": 2,
        "average_depth": None,
        "nodes_per_second": None,
    }
    write_json(run_dir / "results.json", results)

    summary = f"""# {run_name}

> Synthetic smoke-test fixture. These values are fabricated and are not engine-strength results.

- Games: 1 (W/D/L: 1/0/0), score: 100.0%
- SPRT: demo_only
- Completed games: 1; average plies: 2
- Timeouts: 0; illegal moves: 0; engine crashes: 0
- Average depth: not measured; nodes/second: not measured
- Opening results: synthetic fixture (not measured)
- Losses by game phase: not measured
- Engine: Acemi 0.1.0; opponent: Synthetic demo opponent
"""
    (run_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")

    pgn = """[Event \"Acemi synthetic pipeline demo\"]
[Site \"local\"]
[Date \"2026.10.27\"]
[Round \"1\"]
[White \"Acemi demo fixture\"]
[Black \"Synthetic opponent\"]
[Result \"1-0\"]
[Opening \"Synthetic smoke test\"]

1. e4 e5 1-0
"""
    with gzip.open(run_dir / "games.pgn.gz", "wt", encoding="utf-8") as stream:
        stream.write(pgn)

    move = {
        "schema_version": SCHEMA_VERSION,
        "game_no": 1,
        "ply": 1,
        "side": "white",
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        "zobrist_hash": "synthetic-demo",
        "move": "e2e4",
        "eval_cp": 0,
        "depth": None,
        "nodes": None,
        "time_ms": None,
    }
    with gzip.open(run_dir / "moves.jsonl.gz", "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(move, ensure_ascii=False) + "\n")
    with gzip.open(run_dir / "engine.log.gz", "wt", encoding="utf-8") as stream:
        stream.write("Synthetic demo fixture; no chess engine was run.\n")

    positions_dir = ROOT / "data" / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)
    position = {
        "schema_version": SCHEMA_VERSION,
        "is_demo": True,
        "zobrist_hash": "synthetic-demo",
        "fen": move["fen"],
        "occurrences": 1,
        "results": {"wins": 1, "draws": 0, "losses": 0},
        "moves": {"e2e4": 1},
        "average_eval_cp": 0,
    }
    with gzip.open(positions_dir / f"{run_name}.jsonl.gz", "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(position, ensure_ascii=False) + "\n")

    append_index(
        {
            "run_name": run_name,
            "date": date_key,
            "engine_version": "0.1.0",
            "opponent": "Synthetic demo opponent",
            "games": 1,
            "score_pct": "100.0",
            "elo_diff": "",
            "sprt_decision": "demo_only",
        }
    )
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Optional stable date key for repeatable local checks")
    args = parser.parse_args()
    run_dir = create_demo_run(args.date)
    print(f"Created synthetic demo run: {run_dir.relative_to(ROOT).as_posix()}")
    print("Fixture only: the recorded chess result is fabricated.")


if __name__ == "__main__":
    main()
