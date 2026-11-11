"""Identity and resume guards for Stockfish game analysis (no engine searches)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import chess

ANALYSIS_SOURCES = (
    "analyze_games.py", "analysis_config.py", "analysis_schema.py",
    "analysis_inputs.py", "analysis_artifacts.py",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(configuration: dict) -> str:
    payload = json.dumps(configuration, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def analysis_configuration(stockfish: Path, depth: int, syzygy: Path | None = None) -> dict:
    """Hash content, not install paths or timestamps; relocation must preserve identity."""
    if depth < 1:
        raise ValueError("Analysis depth must be positive")
    tables = []
    if syzygy is not None:
        if not syzygy.is_dir():
            raise ValueError(f"Syzygy directory not found: {syzygy}")
        tables = [{"name": path.name, "sha256": file_sha256(path)}
                  for path in sorted(syzygy.glob("*.rtbw"))]
        if not tables:
            raise ValueError(f"No Syzygy WDL tables in {syzygy}; omit --syzygy for Stockfish-only labels")
    source_dir = Path(__file__).resolve().parent
    return {
        "identity_version": 1,
        "depth": depth,
        "stockfish_sha256": file_sha256(stockfish),
        "stockfish_options": {"Threads": 1, "Hash": 64},
        "python_chess_version": chess.__version__,
        "analysis_sources": {name: file_sha256(source_dir / name)
                             for name in ANALYSIS_SOURCES},
        "syzygy_wdl": tables,
    }


def active_fingerprint(out_dir: Path) -> str | None:
    path = out_dir / "config.json"
    if not path.exists():
        return None  # Read-only support for historical, untagged analysis.
    config = json.loads(path.read_text(encoding="utf-8"))
    identity = config.get("analysis_configuration")
    value = config.get("analysis_fingerprint")
    if value is not None and (not isinstance(identity, dict) or fingerprint(identity) != value):
        raise ValueError(f"Invalid analysis identity in {path}")
    return value


def prepare_output(out_dir: Path, configuration: dict, **metadata) -> str:
    """Create once, or require the same identity before changing any existing output."""
    value = fingerprint(configuration)
    path = out_dir / "config.json"
    if path.exists():
        if active_fingerprint(out_dir) != value:
            raise ValueError(f"Analysis configuration differs or is legacy in {out_dir}; use a new --out directory")
        return value
    artifacts = ("parts.json", "parts", "cache", "games.csv", "blunders.csv", "positions.csv.gz")
    if any((out_dir / name).exists() for name in artifacts):
        raise ValueError(f"Analysis artifacts have no verified configuration in {out_dir}; use a new --out directory")
    out_dir.mkdir(parents=True, exist_ok=True)
    config = {**metadata, "analysis_fingerprint": value, "analysis_configuration": configuration}
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(config, indent=1), encoding="utf-8")
    os.replace(temporary, path)
    return value
