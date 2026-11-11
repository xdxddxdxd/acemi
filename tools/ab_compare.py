"""Pinned, paired Kaggle A/B experiment. This module never launches matches on a PC."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import random
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools import match
from tools.match_openings import load_openings

ROOT = Path(__file__).resolve().parents[1]
OLD_COMMIT = "db058b344df8759810e957f11a58b4149055fe49"
NEW_COMMIT = "4068a0459f8119274014cd466270a2ffd3cd30c3"
RUNNER_SOURCES = ("ab_compare.py", "match.py", "match_game.py", "match_config.py",
                  "match_openings.py", "uci_client.py", "record.py", "pairing.py", "elo.py", "summarize.py")
ARTIFACTS = ("meta.json", "results.json", "SUMMARY.md", "games.pgn.gz", "moves.jsonl.gz", "engine.log.gz")


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def source_info(path, expected):
    path = Path(path).resolve()
    actual = _git(path, "rev-parse", "HEAD")
    if actual != expected:
        raise ValueError(f"Source commit mismatch at {path}: {actual} != {expected}")
    if _git(path, "status", "--porcelain", "--untracked-files=all", "--", "engine", "openings"):
        raise ValueError(f"Source engine/openings are dirty: {path}")
    return {"path": str(path), "commit": actual, "engine_tree": _git(path, "rev-parse", "HEAD:engine")}


def _runner_hashes():
    return {name: _sha(ROOT / "tools" / name) for name in RUNNER_SOURCES}


def prepare(out, new_source, old_source, *, games=100, chunk_games=10, movetime_ms=100,
            concurrency=2, hash_mb=16, max_plies=400, seed=1):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f"Session already exists; use its saved protocol to resume: {out}")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", out.name):
        raise ValueError("Use an alphanumeric session id with underscores/hyphens")
    if games < 2 or games % 2 or chunk_games < 2 or chunk_games % 2:
        raise ValueError("Game and chunk counts must be positive even numbers")
    if min(movetime_ms, concurrency, hash_mb, max_plies) < 1 or max_plies > 1000:
        raise ValueError("Invalid time, concurrency, hash or ply limit")
    sources = {"new": source_info(new_source, NEW_COMMIT), "old": source_info(old_source, OLD_COMMIT)}
    if _git(ROOT, "rev-parse", "HEAD:engine") != sources["new"]["engine_tree"]:
        raise ValueError("Collector board implementation differs from the pinned new engine")
    opening_file = Path(new_source) / "openings" / "acemi-64.txt"
    _, openings = load_openings(opening_file)
    if games // 2 > len(openings) or len({(x.start_fen, x.moves) for x in openings}) != len(openings):
        raise ValueError("Not enough distinct paired openings for the requested games")
    selected = random.Random(seed).sample(openings, games // 2)
    out.mkdir(parents=True)
    chunks = []
    for start in range(0, games, chunk_games):
        number = len(chunks) + 1
        count = min(chunk_games, games - start)
        path = out / "openings" / f"chunk_{number:02d}.txt"
        path.parent.mkdir(exist_ok=True)
        lines = selected[start // 2:(start + count) // 2]
        path.write_text("\n".join(x.start_fen or " ".join(x.moves) for x in lines) + "\n", encoding="utf-8")
        chunks.append({"number": number, "games": count, "global_game_start": start + 1,
                       "seed": seed + start, "openings": str(path.relative_to(out)), "sha256": _sha(path)})
    plan = {"schema_version": 1, "id": out.name, "created_at": _utc(), "session_dir": str(out),
            "repo_root": str(ROOT), "sources": sources, "runner_sources": _runner_hashes(),
            "collector_commit": _git(ROOT, "rev-parse", "HEAD"), "games": games, "chunk_games": chunk_games,
            "movetime_ms": movetime_ms, "hash_mb": hash_mb, "max_plies": max_plies,
            "concurrency": min(concurrency, os.cpu_count() or 1), "threads_per_engine": 1,
            "opening_book": False, "sprt_enabled": False, "timeout_grace_ms": 1000,
            "forfeit_policy": "loss_for_either_engine",
            "opening_source_sha256": _sha(opening_file), "selection_seed": seed, "chunks": chunks,
            "runtime": platform.python_implementation(), "runtime_version": platform.python_version()}
    plan["protocol_sha256"] = _digest(plan)
    _write(out / "protocol.json", plan)
    summarize(plan)
    return plan


def load_plan(out):
    out = Path(out).resolve()
    plan = _read(out / "protocol.json")
    payload = {key: value for key, value in plan.items() if key != "protocol_sha256"}
    if _digest(payload) != plan["protocol_sha256"] or plan["session_dir"] != str(out):
        raise ValueError("Experiment protocol identity/path differs")
    if plan["runner_sources"] != _runner_hashes():
        raise ValueError("Match runner code changed; use a new experiment id instead of mixing results")
    for label, commit in (("new", NEW_COMMIT), ("old", OLD_COMMIT)):
        info = plan["sources"][label]
        if info != source_info(info["path"], commit):
            raise ValueError(f"Pinned {label} source differs")
    if _git(ROOT, "rev-parse", "HEAD:engine") != plan["sources"]["new"]["engine_tree"]:
        raise ValueError("Collector engine changed")
    for chunk in plan["chunks"]:
        if _sha(out / chunk["openings"]) != chunk["sha256"]:
            raise ValueError("Paired opening file changed")
    return plan


def experiment_meta(plan, chunk):
    return {"schema_version": 1, "id": plan["id"], "chunk": chunk["number"],
            "protocol_sha256": plan["protocol_sha256"], "new": plan["sources"]["new"],
            "old": plan["sources"]["old"], "global_game_start": chunk["global_game_start"]}


def match_arguments(plan, chunk):
    executable = [sys.executable, "-u", "-m", "engine"]
    command = subprocess.list2cmdline(executable) if os.name == "nt" else shlex.join(executable)
    return ["--games", str(chunk["games"]), "--movetime-ms", str(plan["movetime_ms"]),
            "--concurrency", str(plan["concurrency"]), "--hash-mb", str(plan["hash_mb"]),
            "--max-plies", str(plan["max_plies"]), "--grace-ms", str(plan["timeout_grace_ms"]),
            "--seed", str(chunk["seed"]), "--engine-cmd", command,
            "--engine-cwd", plan["sources"]["new"]["path"], "--opponent-cmd", command,
            "--opponent-cwd", plan["sources"]["old"]["path"],
            "--engine-option", "OwnBook=false", "--opponent-option", "OwnBook=false",
            "--openings", str(Path(plan["session_dir"]) / chunk["openings"]),
            "--git-commit", NEW_COMMIT, "--root", plan["repo_root"]]


def _runs(plan, chunk):
    found = []
    for path in (Path(plan["repo_root"]) / "data" / "runs").glob(f"*_{plan['id']}_c{chunk['number']:02d}/meta.json"):
        meta = _read(path)
        tag = meta.get("experiment", {})
        if tag.get("id") == plan["id"] and tag.get("chunk") == chunk["number"]:
            if tag != experiment_meta(plan, chunk):
                raise ValueError("Existing run belongs to a different experiment protocol")
            found.append(path.parent)
    if len(found) > 1:
        raise ValueError("Duplicate completed runs for one chunk; inspect the raw records")
    return found


def _validate_run(plan, chunk, run):
    meta, result = _read(run / "meta.json"), _read(run / "results.json")
    if (meta.get("experiment") != experiment_meta(plan, chunk)
            or meta["git_commit"] != NEW_COMMIT or meta["match_settings"]["games_requested"] != chunk["games"]
            or meta["engine_settings"]["move_time_ms"] != plan["movetime_ms"]
            or meta["engine_settings"]["hash_mb"] != plan["hash_mb"]
            or meta["engine_settings"]["random_seed"] != chunk["seed"]
            or meta["match_settings"]["forfeit_policy"] != plan["forfeit_policy"]
            or meta["engine_settings"]["opening_book"] is not False
            or meta["opponent"]["opening_book"] is not False
            or result["sprt"]["enabled"] is not False
            or result["games"] + result.get("aborted_games", 0) != chunk["games"]):
        raise ValueError("Recorded chunk does not match the fixed A/B protocol")
    index = Path(plan["repo_root"]) / "data" / "index.csv"
    with index.open(encoding="utf-8", newline="") as stream:
        if not any(row["run_name"] == run.name for row in csv.DictReader(stream)):
            raise ValueError("Raw run has no finalized index row; retain it and inspect the interrupted write")
    return {name: _sha(run / name) for name in ARTIFACTS}, result


def _checkpoint_path(plan, chunk):
    return Path(plan["session_dir"]) / "chunks" / f"chunk_{chunk['number']:02d}.json"


def _record_checkpoint(plan, chunk, run):
    hashes, _ = _validate_run(plan, chunk, run)
    _write(_checkpoint_path(plan, chunk), {"schema_version": 1, "chunk": chunk["number"],
           "run_name": run.name, "file_sha256": hashes, "finished_at": _utc()})


def _checkpoint_result(plan, chunk):
    state = _read(_checkpoint_path(plan, chunk))
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", state["run_name"]):
        raise ValueError("Invalid recorded run name")
    run = Path(plan["repo_root"]) / "data" / "runs" / state["run_name"]
    hashes, result = _validate_run(plan, chunk, run)
    if hashes != state["file_sha256"]:
        raise ValueError("A completed raw run changed; it must not be replayed or overwritten")
    return result


def summarize(plan):
    totals = {key: 0 for key in ("games", "wins", "draws", "losses", "aborted_games", "timeouts",
                                "illegal_moves", "engine_crashes", "board_disagreements",
                                "opponent_timeouts", "opponent_illegal_moves", "opponent_engine_crashes")}
    completed = []
    for chunk in plan["chunks"]:
        if _checkpoint_path(plan, chunk).exists():
            result = _checkpoint_result(plan, chunk)
            for key in totals:
                totals[key] += result.get(key, 0)
            completed.append(chunk["number"])
    attempts = totals["games"] + totals["aborted_games"]
    status = "completed_with_aborts" if totals["aborted_games"] else "completed"
    summary = {"schema_version": 1, "id": plan["id"], "protocol_sha256": plan["protocol_sha256"],
               "status": status if len(completed) == len(plan["chunks"]) else "in_progress",
               "requested_games": plan["games"], "recorded_attempts": attempts,
               "completed_chunks": completed, **totals,
               "score_pct": 100 * (totals["wins"] + totals["draws"] / 2) / totals["games"] if totals["games"] else None,
               "score_perspective": "new engine (all eight changes)", "updated_at": _utc()}
    out = Path(plan["session_dir"])
    _write(out / "results.json", summary)
    text = (f"# A/B: {plan['id']}\n\n- New: `{NEW_COMMIT}`\n- Old: `{OLD_COMMIT}`\n"
            f"- Status: {summary['status']}; chunks {len(completed)}/{len(plan['chunks'])}\n"
            f"- Requested games: {plan['games']}; recorded attempts: {attempts}; counted: {totals['games']}\n"
            f"- New W/D/L: {totals['wins']}/{totals['draws']}/{totals['losses']}\n"
            f"- New score (%): {summary['score_pct']}\n"
            f"- Move time: {plan['movetime_ms']} ms; Hash: {plan['hash_mb']} MB; Threads: 1; OwnBook: false; SPRT: off\n"
            f"- Aborted: {totals['aborted_games']}; new timeouts/illegal/crashes: "
            f"{totals['timeouts']}/{totals['illegal_moves']}/{totals['engine_crashes']}\n"
            f"- Old timeouts/illegal/crashes: {totals['opponent_timeouts']}/{totals['opponent_illegal_moves']}/{totals['opponent_engine_crashes']}\n"
            f"- Board disagreements: {totals['board_disagreements']}\n\n"
            "Colour-swapped pairs use the same opening. Either engine loses on timeout/illegal move/crash. "
            "Internal worker errors are recorded as aborted. Raw per-chunk records are under data/runs/. "
            "Chunk Elo estimates are not the full experiment estimate.\n")
    (out / "SUMMARY.md").write_text(text, encoding="utf-8")
    return summary


class _Tee:
    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text)
        self.log.write(text)
        return len(text)

    def flush(self):
        self.stream.flush()
        self.log.flush()


def run_chunk(plan, number, *, retry_incomplete=False):
    import contextlib
    chunk = next((item for item in plan["chunks"] if item["number"] == number), None)
    if chunk is None:
        raise ValueError("Unknown chunk number")
    if _checkpoint_path(plan, chunk).exists():
        _checkpoint_result(plan, chunk)
        print(f"Chunk {number} already recorded; no games repeated.")
        return summarize(plan)
    existing = _runs(plan, chunk)
    if existing:
        _record_checkpoint(plan, chunk, existing[0])  # Recover a completed run after a lost notebook push.
        return summarize(plan)
    out = Path(plan["session_dir"])
    started = out / "chunks" / f"chunk_{number:02d}.started.json"
    if started.exists() and not retry_incomplete:
        raise ValueError("Chunk started without a finalized run. Stop the old Kaggle session before using --retry-incomplete")
    if not started.exists():
        started.parent.mkdir(parents=True, exist_ok=True)
        with started.open("x", encoding="utf-8") as stream:
            json.dump({"schema_version": 1, "started_at": _utc(), "pid": os.getpid()}, stream)
    log = out / "chunks" / f"chunk_{number:02d}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}.log"
    try:
        with log.open("x", encoding="utf-8") as stream, \
             contextlib.redirect_stdout(_Tee(sys.stdout, stream)), \
             contextlib.redirect_stderr(_Tee(sys.stderr, stream)):
            code = match.main(match_arguments(plan, chunk), experiment=experiment_meta(plan, chunk))
        found = _runs(plan, chunk)
        if code or len(found) != 1:
            raise RuntimeError(f"Chunk {number} failed; raw/log records retained, exit={code}")
        _record_checkpoint(plan, chunk, found[0])
    finally:
        summarize(plan)
    return summarize(plan)


def _on_kaggle():
    return Path("/kaggle/working").is_dir()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--out", type=Path, required=True)
    prep.add_argument("--new-source", type=Path, required=True)
    prep.add_argument("--old-source", type=Path, required=True)
    for flag, default in (("games", 100), ("chunk-games", 10), ("movetime-ms", 100),
                          ("concurrency", 2), ("hash-mb", 16), ("max-plies", 400), ("seed", 1)):
        prep.add_argument("--" + flag, type=int, default=default)
    run = commands.add_parser("run")
    run.add_argument("--session", type=Path, required=True)
    run.add_argument("--chunk", type=int, required=True)
    run.add_argument("--retry-incomplete", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            values = vars(args).copy()
            values.pop("command")
            plan = prepare(**values)
            print(f"Prepared {plan['games']} games in {len(plan['chunks'])} paired chunks: {args.out}")
        else:
            if not _on_kaggle():
                raise ValueError("Match execution is Kaggle-only; no local PC matches are started")
            result = run_chunk(load_plan(args.session), args.chunk, retry_incomplete=args.retry_incomplete)
            print(json.dumps(result, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"A/B experiment stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
