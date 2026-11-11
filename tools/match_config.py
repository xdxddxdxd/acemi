"""Match CLI settings and host/source metadata; no engines are launched here."""

from __future__ import annotations

import argparse
import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


STOCKFISH_CANDIDATES = ("/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish")

def _split_name_version(raw: str) -> tuple[str, str]:
    parts = raw.split()
    if len(parts) >= 2 and parts[-1][:1].isdigit():
        return " ".join(parts[:-1]), parts[-1]
    return raw or "unknown", "unknown"

def _git_info(root: Path, override: str | None = None) -> dict:
    def run(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return done.stdout.strip()

    commit = override.strip() if override else run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"commit": commit, "dirty": None if status is None else bool(status)}

def _ram_mb() -> int | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as stream:
            for line in stream:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None

def _cpu_model() -> str | None:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None

def _find_stockfish(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    found = shutil.which("stockfish")
    if found:
        return found
    for candidate in STOCKFISH_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None

def _split_command(text: str) -> list[str]:
    return shlex.split(text, posix=(os.name != "nt"))

def parse_option_assignments(items: list[str] | None) -> list[list]:
    """Turn ``Name=Value`` strings into [name, value, required] option entries.

    ``true``/``false`` become booleans and digits become integers. They are required:
    an engine that does not declare the option makes the preflight fail instead of
    silently playing with the default (a typo must not produce a fake A/B test).
    """
    options: list[list] = []
    for item in items or []:
        name, separator, raw = item.partition("=")
        name, raw = name.strip(), raw.strip()
        if not separator or not name or not raw:
            raise ValueError(f"option {item!r} must look like Name=Value")
        lowered = raw.lower()
        if lowered in ("true", "false"):
            value: str | int | bool = lowered == "true"
        elif raw.lstrip("-").isdigit():
            value = int(raw)
        else:
            value = raw
        options.append([name, value, True])
    return options

def parse_args(argv: list[str] | None, *, description: str | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--games", type=int, default=20, help="games to play (maximum with --sprt)")
    parser.add_argument("--movetime-ms", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=None, help="parallel games (default: cores - 1)")
    parser.add_argument("--uci-elo", type=int, default=None, help="Stockfish UCI_Elo (default 1320 for Stockfish)")
    parser.add_argument("--stockfish-path", default=None)
    parser.add_argument("--opponent-cmd", default=None, help="any UCI engine command instead of Stockfish")
    parser.add_argument("--opponent-cwd", default=None)
    parser.add_argument("--engine-cmd", default=None, help="engine under test (default: python -m engine)")
    parser.add_argument("--engine-cwd", default=None)
    parser.add_argument("--openings", default=None, help="opening file (FEN/EPD or UCI-move lines)")
    parser.add_argument(
        "--engine-option", action="append", default=[], metavar="NAME=VALUE",
        help="extra UCI option for the engine under test (repeatable), e.g. NullMove=false",
    )
    parser.add_argument(
        "--opponent-option", action="append", default=[], metavar="NAME=VALUE",
        help="extra UCI option for the opponent (repeatable), e.g. NullMove=false",
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--hash-mb", type=int, default=16)
    parser.add_argument("--max-plies", type=int, default=400)
    parser.add_argument("--grace-ms", type=int, default=1000, help="extra time allowed beyond movetime")
    parser.add_argument("--sprt", action="store_true", help="stop early when the SPRT decides")
    parser.add_argument("--elo0", type=float, default=0.0)
    parser.add_argument("--elo1", type=float, default=10.0)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--beta", type=float, default=0.05)
    parser.add_argument("--root", default=str(ROOT), help="repository root that receives data/")
    parser.add_argument(
        "--git-commit", default=None, metavar="HASH",
        help="record this code commit instead of git rev-parse HEAD (data pushes do not advance it)",
    )
    parser.add_argument("--no-record", action="store_true", help="print the summary, write nothing")
    return parser.parse_args(argv)
