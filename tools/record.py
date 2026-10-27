"""Write run artifacts under data/ using schema v1 (see AGENT_GUIDE.md).

Runs are immutable: a run directory is created once and never rewritten. The
position database is the only merged data: ``data/positions/<xx>.jsonl.gz``
shards (``xx`` = first two hex digits of the Zobrist hash) are updated in place
by merging new counts into existing entries.
"""

from __future__ import annotations

import csv
import gzip
import json
from collections.abc import Iterable
from pathlib import Path

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


def write_gzip_text(path: Path, text: str) -> None:
    """Write gzip text with no filename/mtime so identical content gives identical bytes."""
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            stream.write(text.encode("utf-8"))


def read_gzip_text(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return stream.read()


def write_run(
    root: Path,
    run_name: str,
    meta: dict,
    results: dict,
    summary_md: str,
    pgn_text: str,
    moves: Iterable[dict],
    engine_log: str,
) -> Path:
    """Create ``data/runs/<run_name>/`` with all six artifacts. Refuses to overwrite."""
    run_dir = root / "data" / "runs" / run_name
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists (runs are immutable): {run_dir}")
    run_dir.mkdir(parents=True)

    write_json(run_dir / "meta.json", meta)
    write_json(run_dir / "results.json", results)
    (run_dir / "SUMMARY.md").write_text(summary_md, encoding="utf-8")
    write_gzip_text(run_dir / "games.pgn.gz", pgn_text)
    move_lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in moves)
    write_gzip_text(run_dir / "moves.jsonl.gz", move_lines)
    write_gzip_text(run_dir / "engine.log.gz", engine_log)
    return run_dir


def append_index(root: Path, row: dict) -> None:
    """Append one row to data/index.csv unless the run is already listed."""
    index_path = root / "data" / "index.csv"
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


def _shard_path(root: Path, zobrist_hash: str) -> Path:
    return root / "data" / "positions" / f"{zobrist_hash[:2]}.jsonl.gz"


def _load_shard(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    entries: dict[str, dict] = {}
    for line in read_gzip_text(path).splitlines():
        if line.strip():
            entry = json.loads(line)
            entries[entry["zobrist_hash"]] = entry
    return entries


def _outcome_for_mover(game_result: str, side: str) -> str | None:
    """Outcome key (wins/draws/losses) for the side that moved, or None if unknown."""
    if game_result == "1/2-1/2":
        return "draws"
    if game_result == "1-0":
        return "wins" if side == "white" else "losses"
    if game_result == "0-1":
        return "wins" if side == "black" else "losses"
    return None


def update_positions(root: Path, entries: Iterable[tuple[dict, str]]) -> int:
    """Merge (move record, game result) pairs into the position database.

    Counts are from the point of view of the side to move in the recorded FEN.
    Records without a Zobrist hash, or whose game result is unknown ("*"), are
    skipped. Returns the number of move records merged. Call once per run:
    merging the same run twice would double-count it.
    """
    shards: dict[Path, dict[str, dict]] = {}
    merged = 0
    for move, game_result in entries:
        zobrist_hash = move.get("zobrist_hash")
        if not zobrist_hash:
            continue
        outcome = _outcome_for_mover(game_result, str(move["side"]))
        if outcome is None:
            continue

        path = _shard_path(root, zobrist_hash)
        if path not in shards:
            shards[path] = _load_shard(path)
        positions = shards[path]

        entry = positions.get(zobrist_hash)
        if entry is None:
            entry = {
                "schema_version": SCHEMA_VERSION,
                "zobrist_hash": zobrist_hash,
                "fen": move["fen"],
                "occurrences": 0,
                "results": {"wins": 0, "draws": 0, "losses": 0},
                "moves": {},
                "average_eval_cp": None,
                "eval_samples": 0,
            }
            positions[zobrist_hash] = entry

        entry["occurrences"] += 1
        entry["results"][outcome] += 1
        played = str(move["move"])
        entry["moves"][played] = entry["moves"].get(played, 0) + 1

        eval_cp = move.get("eval_cp")
        if isinstance(eval_cp, (int, float)) and not isinstance(eval_cp, bool):
            samples = int(entry.get("eval_samples") or 0)
            previous = entry.get("average_eval_cp") or 0.0
            entry["eval_samples"] = samples + 1
            entry["average_eval_cp"] = (previous * samples + eval_cp) / (samples + 1)
        merged += 1

    for path, positions in shards.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(
            json.dumps(positions[key], ensure_ascii=False) + "\n" for key in sorted(positions)
        )
        write_gzip_text(path, text)
    return merged


def record_run(
    root: Path,
    run_name: str,
    meta: dict,
    results: dict,
    summary_md: str,
    pgn_text: str,
    moves: list[dict],
    engine_log: str,
    position_entries: Iterable[tuple[dict, str]],
    index_row: dict,
) -> Path:
    """Write the run, merge its positions, and index it (in that order)."""
    run_dir = write_run(root, run_name, meta, results, summary_md, pgn_text, moves, engine_log)
    update_positions(root, position_entries)
    append_index(root, index_row)
    return run_dir
