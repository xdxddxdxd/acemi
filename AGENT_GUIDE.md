# Acemi analysis agent guide

## Repository map

- `engine/`: chess engine. The engine core is standard-library-only; do not use `python-chess` here.
- `tools/`: match, recording, Stockfish/UCI integration, and analysis utilities. `python-chess` is allowed only here.
- `tests/`: correctness tests and tactical positions.
- `notebooks/kaggle_runner.ipynb`: run tests, save raw results, and push them. It must not make analysis or strength decisions.
- `data/`: machine-readable run results. `data/runs/<run_name>/` holds immutable run artifacts; `data/index.csv` is the run index.
- `analysis/`: analysis-agent output only. The coding agent and Kaggle runner must not write here.

## Read and write protocol

1. Read `data/runs/<run_name>/SUMMARY.md` first.
2. If a claim needs checking, inspect `results.json`, then the compressed PGN, move stream, or engine log as needed.
3. Write one report to `analysis/<run_name>.md` and update `analysis/NEXT.md` with the next proposed experiment.
4. Never edit engine code, `data/`, or the Kaggle notebook. Do not alter raw run records.
5. Separate measured facts from hypotheses. Stockfish `UCI_Elo` comparisons are rough and are not directly comparable with Lichess/CCRL ratings.

## Schema version 1

All JSON documents and JSONL records include `schema_version: 1`. Increment the schema version and update this guide when changing the format.

### `meta.json`

Contains `run_name`, `date`, `engine_version`, `git_commit`, `engine_settings` (`move_time_ms`, `hash_mb`, `random_seed`, `opening_book`), `opponent` (`name`, `version`, `uci_elo`), `opening_set`, `hardware` (`cpu_count`, `ram_mb`, `runtime`, `runtime_version`), and UTC `started_at`/`finished_at`. `is_demo: true` identifies fabricated pipeline fixtures; never treat their chess results as measurements.

### `results.json`

Contains game count and W/D/L, `score_pct`, Elo estimate and confidence interval (nullable), SPRT parameters/result, W/D/L by color, optional tactics result, plus timeout, illegal-move, crash, average-ply, average-depth, and nodes/second fields. Null means not measured, not zero.

### `SUMMARY.md`

Human-readable factual summary of the same run. It must not contain causal analysis or recommendations. Demo summaries explicitly state that values are synthetic.

### Additions in the Stage 2 writer (still schema version 1)

Real runs add fields; absent fields in older demo runs mean not recorded.

- `meta.json`: `engine_name`, `git_dirty`, `match_settings` (`games_requested`, `concurrency`, `max_plies`, `timeout_grace_ms`, `pairing`).
- `results.json`: `aborted_games`, `unpaired_games_excluded`, `board_disagreements`; `sprt` gains `enabled`, `max_games`, `lower_bound`, `upper_bound`. Decisions: `accept_h1`, `accept_h0`, `inconclusive`, `not_run`, `demo_only`. With SPRT, W/D/L and Elo use only completed colour-swapped pairs; unpaired games remain in raw artifacts but are excluded from the result.
- `games` counts completed games only. A game where the opponent crashed, timed out or played illegally is `aborted` and excluded from W/D/L. If Acemi does that, the game is a recorded loss.
- `moves.jsonl.gz` records add `player` (`engine` or `opponent`), `eval_mate`; `zobrist_hash` is a 16-digit hex string, or null after an Acemi/python-chess board disagreement.
- Position database: `data/positions/<xx>.jsonl.gz` shards (xx = first two hex digits of the hash), merged across runs; counts are from the side to move's view. Extra fields `eval_samples`. Entries from demo runs live in per-run files and carry `is_demo: true`.
- Acemi's `eval_cp`, `depth` and `nodes` are null until search exists (not measured, not zero).

### Compressed artifacts

- `games.pgn.gz`: PGN games with run metadata and outcomes.
- `moves.jsonl.gz`: one JSON object per ply with `game_no`, `ply`, `side`, `fen`, `zobrist_hash`, `move`, `eval_cp`, `depth`, `nodes`, and `time_ms`.
- `engine.log.gz`: captured engine output/log.
- `data/positions/*.jsonl.gz`: position aggregates with `zobrist_hash`, `fen`, `occurrences`, W/D/L `results`, move counts, and `average_eval_cp`.

### `data/index.csv`

One row per run: `run_name,date,engine_version,opponent,games,score_pct,elo_diff,sprt_decision`.
