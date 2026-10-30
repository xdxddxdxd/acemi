"""Build a small Polyglot opening book from the accepted opening set.

At every node of a selected line, Stockfish's top moves (MultiPV) are added when
they are within ``--cp-window`` of the best move; the line move itself is always
kept. Only one path per branch is traversed, so the book stays small.

    python -m tools.bookgen --stockfish /path/to/stockfish \
        --openings openings/acemi-64.txt --out openings/book.bin
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import chess
import chess.polyglot
import chess.engine

from tools.polyglot import encode_move, write_book


def load_lines(path: Path) -> list[tuple[str, list[str]]]:
    lines: list[tuple[str, list[str]]] = []
    name = "line"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            name = line.lstrip("# ").split(" (")[0]
            continue
        lines.append((name, line.split()))
    return lines


def select_branches(lines: list[tuple[str, list[str]]], count: int) -> list[tuple[str, list[str]]]:
    if count >= len(lines):
        return lines
    indices = sorted({round(i * (len(lines) - 1) / (count - 1)) for i in range(count)}) if count > 1 else [0]
    if len(indices) < count:
        for index in range(len(lines)):
            if index not in indices:
                indices.append(index)
            if len(indices) == count:
                break
    return [lines[index] for index in sorted(indices[:count])]


def build_entries(
    openings: list[tuple[str, list[str]]],
    evaluator,
    *,
    max_plies: int = 12,
    depth: int = 12,
    cp_window: int = 30,
) -> dict[int, dict[int, int]]:
    entries: dict[int, dict[int, int]] = {}
    for _name, moves in openings:
        board = chess.Board()
        for ply in range(max_plies):
            results = evaluator.multipv(board, depth)
            if not results:
                break
            best_cp = results[0][1]
            line_move = chess.Move.from_uci(moves[ply]) if ply < len(moves) else None
            if line_move is not None and line_move not in board.legal_moves:
                break
            chosen = line_move if line_move is not None else results[0][0]
            key = chess.polyglot.zobrist_hash(board)
            slot = entries.setdefault(key, {})
            for move, cp in results:
                if abs(cp - best_cp) <= cp_window:
                    code = encode_move(board, move)
                    weight = 10 if move == chosen else 5
                    slot[code] = max(slot.get(code, 0), weight)
            if line_move is not None:
                code = encode_move(board, line_move)
                slot[code] = max(slot.get(code, 0), 10)
            board.push(chosen)
            if not board.legal_moves:
                break
    return entries


class StockfishEvaluator:
    def __init__(self, path: str) -> None:
        self.engine = chess.engine.SimpleEngine.popen_uci(path)
        self.engine.configure({"Threads": 1, "Hash": 64})

    def multipv(self, board: chess.Board, depth: int) -> list[tuple[chess.Move, int]]:
        infos = self.engine.analyse(board, chess.engine.Limit(depth=depth), multipv=3)
        results: list[tuple[chess.Move, int]] = []
        for info in infos:
            score = info.get("score")
            pv = info.get("pv")
            if score is None or not pv:
                continue
            white = score.pov(chess.WHITE)
            cp = 10000 if white.is_mate() and white.mate() > 0 else -10000 if white.is_mate() else white.score()
            results.append((pv[0], cp))
        return results

    def close(self) -> None:
        self.engine.quit()


def find_stockfish(explicit: str | None) -> str:
    if explicit:
        return explicit
    for candidate in ("stockfish", "/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"):
        found = shutil.which(candidate) if not candidate.startswith("/") else candidate
        if found and Path(found).exists():
            return found
    raise FileNotFoundError("Stockfish not found; pass --stockfish PATH")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a small Polyglot book from balanced openings.")
    parser.add_argument("--openings", type=Path, default=Path("openings/acemi-64.txt"))
    parser.add_argument("--out", type=Path, default=Path("openings/book.bin"))
    parser.add_argument("--stockfish", default=None)
    parser.add_argument("--branches", type=int, default=24)
    parser.add_argument("--max-plies", type=int, default=12)
    parser.add_argument("--depth", type=int, default=12)
    parser.add_argument("--cp-window", type=int, default=30)
    args = parser.parse_args(argv)

    lines = load_lines(args.openings)
    branches = select_branches(lines, args.branches)
    print(f"openings: {len(lines)}, branches: {len(branches)}")
    evaluator = StockfishEvaluator(find_stockfish(args.stockfish))
    try:
        entries = build_entries(
            branches,
            evaluator,
            max_plies=args.max_plies,
            depth=args.depth,
            cp_window=args.cp_window,
        )
    finally:
        evaluator.close()
    write_book(args.out, entries)
    moves = sum(len(slot) for slot in entries.values())
    print(f"positions: {len(entries)}, moves: {moves}, wrote {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
