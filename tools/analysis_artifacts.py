"""Immutable analysis parts, checksum/identity validation and CSV aggregation."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import chess

from tools.analysis_config import active_fingerprint
from tools.analysis_schema import POSITION_FIELDS, GAME_FIELDS, BLUNDER_FIELDS


PARTS_DIR = "parts"

PARTS_MANIFEST = "parts.json"

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

def _atomic_write(path: Path, write) -> None:
    """Write through a temporary file, then rename: readers never see half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    write(temporary)
    os.replace(temporary, path)

def part_id(game_ids, identity: str | None = None) -> str:
    """Content-based id: the same set of games always gives the same part."""
    content = "\n".join(sorted(game_ids))
    if identity is not None:
        content = identity + "\n" + content
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]

def _part_files(part: str) -> dict[str, str]:
    return {
        "positions": f"{PARTS_DIR}/positions_part_{part}.csv.gz",
        "games": f"{PARTS_DIR}/games_part_{part}.csv",
        "blunders": f"{PARTS_DIR}/blunders_part_{part}.csv",
    }

def read_parts_manifest(out_dir: Path) -> dict:
    path = out_dir / PARTS_MANIFEST
    if not path.exists():
        return {"parts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"parts": []}
    return data if isinstance(data.get("parts"), list) else {"parts": []}

def valid_parts(out_dir: Path) -> tuple[list[dict], list[str]]:
    """Manifest parts whose files exist with the recorded checksums, plus a list of problems."""
    good: list[dict] = []
    problems: list[str] = []
    seen: set[str] = set()
    identity = active_fingerprint(out_dir)
    manifest = read_parts_manifest(out_dir)
    if (out_dir / PARTS_MANIFEST).exists() and manifest.get("analysis_fingerprint") != identity:
        raise ValueError("Part manifest has a different analysis identity; use a new --out directory")
    for part in manifest["parts"]:
        if part.get("analysis_fingerprint") != identity:
            raise ValueError("Part has a different or missing analysis identity; use a new --out directory")
        files = part.get("files", {})
        ids = part.get("game_ids", [])
        broken = [name for name in ("positions", "games", "blunders") if name not in files]
        for name, info in files.items():
            path = out_dir / info.get("path", "")
            if not path.exists() or _sha256(path) != info.get("sha256"):
                broken.append(name)
        if broken or part.get("id") != part_id(ids, identity) or seen.intersection(ids):
            problems.append(f"part {part.get('id')} dropped ({', '.join(sorted(set(broken))) or 'bad id or duplicate games'})")
            continue
        seen.update(ids)
        good.append(part)
    return good, problems

def processed_game_ids(out_dir: Path) -> set[str]:
    ids: set[str] = set()
    for part in valid_parts(out_dir)[0]:
        ids.update(part["game_ids"])
    return ids

def _blunder_category(row: dict) -> str:
    board = chess.Board(row["fen"])
    move = chess.Move.from_uci(row["move"]) if row.get("move") else None
    tactical = bool(move and (board.is_capture(move) or board.gives_check(move) or move.promotion))
    return "tactical" if tactical else "positional"

def seal_part(out_dir: Path) -> dict | None:
    """Turn every cached game that is not yet in a part into one immutable part."""
    cache_dir = out_dir / "cache"
    identity = active_fingerprint(out_dir)
    done = processed_game_ids(out_dir)
    cached: dict[str, dict] = {}
    cache_paths: dict[str, Path] = {}
    for path in sorted(cache_dir.glob("*.json")) if cache_dir.exists() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            path.unlink(missing_ok=True)  # Half-written cache entry: the game is analysed again.
            continue
        if (not isinstance(data, dict) or not isinstance(data.get("game_id"), str)
                or not isinstance(data.get("plies"), list) or not isinstance(data.get("game_stats"), dict)):
            path.unlink(missing_ok=True)
            continue
        if data.get("analysis_fingerprint") != identity:
            raise ValueError(f"Cache {path.name} has a different or missing analysis identity")
        if data["game_id"] in done:
            path.unlink(missing_ok=True)
            continue
        cached[data["game_id"]] = data
        cache_paths[data["game_id"]] = path
    if not cached:
        return None
    ids = sorted(cached)
    part = part_id(ids, identity)
    files = _part_files(part)

    positions = [row for game_id in ids for row in cached[game_id]["plies"]]
    games = [cached[game_id]["game_stats"] for game_id in ids]
    blunders = []
    for row in positions:
        if row["is_acemi"] and row["cp_loss"] is not None and row["cp_loss"] > 150:
            blunders.append({**row, "category": _blunder_category(row)})

    def write_positions(path: Path) -> None:
        with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=POSITION_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(positions)

    def csv_writer(fields: list[str], rows: list[dict]):
        def write(path: Path) -> None:
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

        return write

    _atomic_write(out_dir / files["positions"], write_positions)
    _atomic_write(out_dir / files["games"], csv_writer(GAME_FIELDS, games))
    _atomic_write(out_dir / files["blunders"], csv_writer(BLUNDER_FIELDS, blunders))
    entry = {
        "id": part,
        "analysis_fingerprint": identity,
        "game_ids": ids,
        "rows": {"positions": len(positions), "games": len(games), "blunders": len(blunders)},
        "files": {name: {"path": path, "sha256": _sha256(out_dir / path)} for name, path in files.items()},
        "sealed_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest = {"analysis_fingerprint": identity,
                "parts": [item for item in valid_parts(out_dir)[0] if item["id"] != part] + [entry]}
    # The manifest is written last: until then the new files are unreferenced and harmless.
    _atomic_write(
        out_dir / PARTS_MANIFEST,
        lambda path: path.write_text(json.dumps(manifest, indent=1), encoding="utf-8"),
    )
    for path in cache_paths.values():
        path.unlink(missing_ok=True)  # The sealed part is now the source of truth.
    return entry

def _read_csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))

def aggregate(out_dir: Path) -> dict:
    """Rebuild the small merged files (games.csv, blunders.csv) from the sealed parts.

    Positions are never merged: the report reads the part files directly.
    """
    parts, problems = valid_parts(out_dir)
    games: list[dict] = []
    blunders: list[dict] = []
    positions = 0
    for part in parts:
        games.extend(_read_csv_rows(out_dir / part["files"]["games"]["path"]))
        blunders.extend(_read_csv_rows(out_dir / part["files"]["blunders"]["path"]))
        positions += part["rows"]["positions"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, fields, rows in (("games.csv", GAME_FIELDS, games), ("blunders.csv", BLUNDER_FIELDS, blunders)):
        def write(path: Path, fields=fields, rows=rows) -> None:
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

        _atomic_write(out_dir / name, write)
    ids = sorted(game["game_id"] for game in games)
    (out_dir / "processed_games.txt").write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
    return {"parts": len(parts), "games": len(games), "positions": positions, "blunders": len(blunders),
            "problems": problems}
