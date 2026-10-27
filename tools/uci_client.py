"""Minimal blocking UCI client for the match runner (tools only).

It talks to any UCI engine over pipes. Failures are reported precisely so the
runner can tell apart a timeout, a crash, and a setup problem.
"""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from dataclasses import dataclass


class EngineError(Exception):
    """Base class for engine communication failures."""


class EngineSetupError(EngineError):
    """The engine could not be started or configured as requested."""


class EngineTimeout(EngineError):
    """The engine did not answer within the allowed time."""


class EngineCrashed(EngineError):
    """The engine process exited or its pipe broke."""


@dataclass(frozen=True)
class UciOption:
    name: str
    kind: str
    default: str | None
    minimum: int | None
    maximum: int | None


@dataclass(frozen=True)
class SearchResult:
    bestmove: str
    depth: int | None
    nodes: int | None
    score_cp: int | None
    score_mate: int | None
    elapsed_ms: int


_OPTION_KEYWORDS = ("name", "type", "default", "min", "max", "var")


def _to_int(tokens: list[str]) -> int | None:
    try:
        return int(tokens[0])
    except (IndexError, ValueError):
        return None


def parse_option_line(line: str) -> UciOption | None:
    """Parse ``option name X type spin default 1 min 0 max 9`` (None if malformed)."""
    tokens = line.split()
    if not tokens or tokens[0] != "option" or "name" not in tokens or "type" not in tokens:
        return None
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for token in tokens[1:]:
        if token in _OPTION_KEYWORDS:
            current = token
            fields.setdefault(current, [])
        elif current is not None:
            fields[current].append(token)
    name = " ".join(fields.get("name", []))
    kind = fields.get("type", [""])[0] if fields.get("type") else ""
    if not name or not kind:
        return None
    default = " ".join(fields["default"]) if fields.get("default") else None
    return UciOption(
        name=name,
        kind=kind,
        default=default,
        minimum=_to_int(fields.get("min", [])),
        maximum=_to_int(fields.get("max", [])),
    )


def parse_info_line(line: str) -> dict[str, int] | None:
    """Extract depth/nodes and cp or mate score from an ``info`` line with a score.

    Returns None for lines without a score, for ``info string`` lines, and for
    bound scores (lowerbound/upperbound), so the last result is an exact score.
    """
    tokens = line.split()
    if len(tokens) < 2 or tokens[0] != "info" or tokens[1] == "string":
        return None
    if "score" not in tokens or "lowerbound" in tokens or "upperbound" in tokens:
        return None
    values: dict[str, int] = {}
    index = 1
    try:
        while index < len(tokens):
            token = tokens[index]
            if token == "pv":
                break
            if token in ("depth", "nodes"):
                values[token] = int(tokens[index + 1])
                index += 2
            elif token == "score":
                values[tokens[index + 1]] = int(tokens[index + 2])  # "cp" or "mate"
                index += 3
            else:
                index += 1
    except (IndexError, ValueError):
        return None
    if "cp" not in values and "mate" not in values:
        return None
    return values


class UciEngine:
    def __init__(
        self,
        command: list[str],
        *,
        label: str,
        cwd: str | None = None,
        log: list[str] | None = None,
    ) -> None:
        self.command = command
        self.label = label
        self.cwd = cwd
        self.log: list[str] = log if log is not None else []
        self.name = "unknown"
        self.options: dict[str, UciOption] = {}
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._process: subprocess.Popen[str] | None = None
        self._threads: list[threading.Thread] = []

    def start(self, timeout_s: float = 20.0) -> None:
        """Launch the process and complete the ``uci`` / ``uciok`` handshake."""
        try:
            self._process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as error:
            raise EngineSetupError(
                f"{self.label}: cannot start {self.command[0]!r}: {error}"
            ) from error
        for target in (self._pump_stdout, self._pump_stderr):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)

        self._send("uci")
        for line in self._wait_for("uciok", timeout_s):
            if line.startswith("id name "):
                self.name = line[len("id name ") :].strip()
            option = parse_option_line(line)
            if option is not None:
                self.options[option.name.lower()] = option

    def set_option(self, name: str, value: str | int | bool, *, required: bool = True) -> bool:
        """Send ``setoption``. Returns False if the option is absent and not required."""
        option = self.options.get(name.lower())
        if option is None:
            if required:
                raise EngineSetupError(f"{self.label} does not declare the UCI option {name!r}")
            return False
        if isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = str(value)
        if option.kind == "spin":
            try:
                number = int(text)
            except ValueError as error:
                raise EngineSetupError(f"{self.label}: option {name!r} needs an integer") from error
            too_low = option.minimum is not None and number < option.minimum
            too_high = option.maximum is not None and number > option.maximum
            if too_low or too_high:
                raise EngineSetupError(
                    f"{self.label}: {name}={number} is outside the supported range "
                    f"{option.minimum}..{option.maximum}"
                )
        self._send(f"setoption name {option.name} value {text}")
        return True

    def ready(self, timeout_s: float = 20.0) -> None:
        self._send("isready")
        self._wait_for("readyok", timeout_s)

    def new_game(self, timeout_s: float = 20.0) -> None:
        self._send("ucinewgame")
        self.ready(timeout_s)

    def search(self, position_command: str, movetime_ms: int, grace_ms: int) -> SearchResult:
        """Run ``go movetime`` and wait for ``bestmove`` (movetime + grace at most)."""
        self._send(position_command)
        started = time.monotonic()
        self._send(f"go movetime {movetime_ms}")
        deadline = started + (movetime_ms + grace_ms) / 1000.0
        info: dict[str, int] = {}
        while True:
            line = self._next_line(deadline)
            if line.startswith("bestmove"):
                parts = line.split()
                move = parts[1] if len(parts) > 1 else ""
                elapsed_ms = int((time.monotonic() - started) * 1000)
                return SearchResult(
                    bestmove=move,
                    depth=info.get("depth"),
                    nodes=info.get("nodes"),
                    score_cp=info.get("cp"),
                    score_mate=info.get("mate"),
                    elapsed_ms=elapsed_ms,
                )
            update = parse_info_line(line)
            if update is not None:
                info = update

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        self._process = None
        try:
            self._write("quit", process)
        except EngineError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for thread in self._threads:
            thread.join(timeout=1)
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except (OSError, ValueError):
                pass

    # -- internals ---------------------------------------------------------

    def _write(self, text: str, process: subprocess.Popen[str]) -> None:
        try:
            assert process.stdin is not None
            process.stdin.write(text + "\n")
            process.stdin.flush()
        except (OSError, ValueError) as error:
            raise EngineCrashed(f"{self.label}: cannot write to engine ({error})") from error

    def _send(self, text: str) -> None:
        if self._process is None:
            raise EngineCrashed(f"{self.label}: engine is not running")
        self._write(text, self._process)

    def _next_line(self, deadline: float) -> str:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise EngineTimeout(f"{self.label}: no answer in time")
        try:
            line = self._lines.get(timeout=remaining)
        except queue.Empty:
            raise EngineTimeout(f"{self.label}: no answer in time") from None
        if line is None:
            raise EngineCrashed(f"{self.label}: engine exited")
        return line

    def _wait_for(self, token: str, timeout_s: float) -> list[str]:
        deadline = time.monotonic() + timeout_s
        seen: list[str] = []
        while True:
            line = self._next_line(deadline)
            seen.append(line)
            if line == token or line.startswith(token + " "):
                return seen

    def _pump_stdout(self) -> None:
        process = self._process
        try:
            assert process is not None and process.stdout is not None
            for raw in process.stdout:
                line = raw.rstrip("\r\n")
                if line.strip():
                    self._lines.put(line.strip())
        except (OSError, ValueError):
            pass
        finally:
            self._lines.put(None)

    def _pump_stderr(self) -> None:
        process = self._process
        try:
            assert process is not None and process.stderr is not None
            for raw in process.stderr:
                self.log.append(f"[{self.label} stderr] {raw.rstrip()}")
        except (OSError, ValueError):
            pass
