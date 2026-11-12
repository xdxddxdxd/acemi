# Acemi analysis agent guide

## Repository map

- `engine/`: chess engine. The engine core is standard-library-only; do not use `python-chess` here.
- `tools/`: match, recording, Stockfish/UCI integration, and analysis utilities. `python-chess` is allowed only here.
  CLI entry points remain unchanged; module responsibilities and compatibility exports
  are documented in `docs/TOOLS.md`. Extracted analysis modules are included in the
  source fingerprint. Historical raw run/analysis artifacts are not migrated or rewritten.
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

- `meta.json`: `engine_name`, `git_dirty`, `match_settings` (`games_requested`, `concurrency`, `max_plies`, `timeout_grace_ms`, `pairing`, `command` = the exact `tools.match` command line), `hardware.cpu_model`.
- `results.json`: `aborted_games`, `unpaired_games_excluded`, `post_decision_games_excluded`, `board_disagreements`; `sprt` gains `enabled`, `max_games`, `lower_bound`, `upper_bound`. Decisions: `accept_h1`, `accept_h0`, `inconclusive`, `not_run`, `demo_only`. With SPRT, W/D/L and Elo use only completed colour-swapped pairs that had finished when the SPRT reached its decision (the sample is frozen at that moment); unpaired games and games that finished afterwards remain in raw artifacts but are excluded from the result (`post_decision_games_excluded` counts the latter, so `sprt.llr` and `sprt.decision` describe exactly the recorded W/D/L). From 0.6.2 the SPRT LLR is the trinomial constrained-maximum-likelihood ratio (see `tools/sprt.py`); decisions recorded for earlier runs used an observed-variance formula that overstated the LLR on extreme records.
- `games` counts completed games only. A game where the opponent crashed, timed out or played illegally is `aborted` and excluded from W/D/L. If Acemi does that, the game is a recorded loss.
- `results.json` also gains `terminations` (game endings of the counted games: `checkmate`, `threefold_repetition`, `fifty_moves`, `insufficient_material`, `stalemate`, `max_plies`, forfeit reasons), `engine_moves`, `engine_moves_without_score` (Acemi moves that returned before any iteration finished: their `eval_cp`/`eval_mate` are null but `depth`/`nodes` are still recorded) and `nodes_per_second_search` (nodes divided by the engine's own `info time`; `nodes_per_second` divides by wall clock including pipe latency).
- `moves.jsonl.gz` records add `search_time_ms` (the engine's own `info time`, null if not reported) and `attempted_depth` (Acemi only: deepest iteration started, which can exceed `depth` when a cut-short iteration supplied the move; null for other engines); they also add `player` (`engine` or `opponent`), `eval_mate`; `zobrist_hash` is a 16-digit hex string, or null after an Acemi/python-chess board disagreement.
- Position database: `data/positions/<xx>.jsonl.gz` shards (xx = first two hex digits of the hash), merged across runs; counts are from the side to move's view. Extra fields `eval_samples`. Entries from demo runs live in per-run files and carry `is_demo: true`.
- Acemi's `eval_cp`, `depth` and `nodes` are null until search exists (not measured, not zero).

- `data/bench/<label>.json`: output of `python -m tools.bench` (fixed-depth search of 10 positions: per position `score`, `depth`, `nodes`, `best_move`, `seconds`; totals and `nodes_per_second`; runtime and CPU). Two builds that search identically must have equal scores, depths, nodes and best moves; only seconds differ. Compare with `python -m tools.bench --compare A.json B.json`.

- `data/baselines/<session>/`: Step 1 reference collection (see `docs/BASELINE.md`).
  `reference/` and `current/` each contain schema-v1 `meta.json`, `tests.json`,
  `results.json`, `bench.json` when tests/benchmark succeed, logs and `SUMMARY.md`.
  Metadata distinguishes the source commit/engine tree from the collector commit.
  Existing records are never overwritten. Failed/zero-test runs are not passing
  references; their logs are still published. `session.json` and `comparison.log`
  describe the fixed-depth comparison, not a strength decision or Elo estimate.
  Step 8 additionally records `engine_tree_matches` / `require_identical_engine_tree`
  and requires unchanged engine files for the tools-only refactor.

### Search profiling (Step 7)

`data/baselines/<session>/profiles/` adds diagnostic schema-v1 profiles for the
reference/current engine trees. Each includes a profiled benchmark and engine
function call counts/self/cumulative time, plus source/collector commits.
Profiled searches must match; their instrumented times are never used as speed
measurements. Use the separate normal `reference/bench.json` / `current/bench.json`
for elapsed-time comparisons. Logs are retained and published on failure too.

### Analysis identity (Step 5)

New `data/analysis/<output>/config.json` records `analysis_configuration` and
`analysis_fingerprint` (identity version 1). Per-game scratch caches, the part
manifest and every part carry that fingerprint; part ids include it. Resuming
with a different/missing identity requires a new output directory. Historical
untagged analyses remain readable; they are not retroactively verified.
See `docs/ANALYSIS.md`. New match metadata adds `book_file` and derives
`opening_book` from advertised defaults plus overrides on both sides (`null`
if unsupported); this records configuration, not a book hit. Existing raw records
are never rewritten to add these fields.

### Compressed artifacts

- `games.pgn.gz`: PGN games with run metadata and outcomes.
- `moves.jsonl.gz`: one JSON object per ply with `game_no`, `ply`, `side`, `fen`, `zobrist_hash`, `move`, `eval_cp`, `depth`, `nodes`, and `time_ms`.
- `engine.log.gz`: captured engine output/log.
- `data/positions/*.jsonl.gz`: position aggregates with `zobrist_hash`, `fen`, `occurrences`, W/D/L `results`, move counts, and `average_eval_cp`.

### Paired old/new A/B experiment

`notebooks/kaggle_ab_100.ipynb` on `codex/ab-100` compares pinned pre-eight-step
`db058b3` with merged `4068a04` for 100 games at 100 ms. Immutable protocols and
per-chunk checkpoints live under `data/ab/<id>/`; raw runs remain under `data/runs/`.
New is always `engine`, old is `opponent`. `meta.json.experiment` records both
full commits/engine trees, protocol identity, chunk and global game offset.
For this experiment only, `match_settings.forfeit_policy=loss_for_either_engine`
counts either engine's timeout/illegal move/crash as a loss. Results additionally
record opponent_timeouts/opponent_illegal_moves/opponent_engine_crashes.
Legacy runs still exclude opponent failures. Aggregate results distinguish
requested games, recorded attempts, counted games and aborted internal failures.

### Quiescence SEE experiment

`codex/quiescence-see` adds `notebooks/kaggle_quiescence_see.ipynb` and
`docs/QUIESCENCE_SEE.md`. Both sides use the same pinned full source commit;
protocol `feature_options.new/old` distinguishes QuiescenceSEE true/false.
The A/B collector validates recorded option overrides against the protocol.
The feature defaults off and orders only non-check quiescence tactical moves;
no capture is pruned. Draw adjudication and time policy are unchanged.
`data/ab/<id>/validation/` records the full Kaggle test log, depth-3 reference,
SEE-off and SEE-on diagnostics, source identity and hashed gate artifacts.
SEE-off must match validated `4068a04` scores/moves/depths/nodes before matches.
Local checks must not invoke `test_quiescence_see_search` or the real validation
worker; all real searches and the single 100-game match run only in Kaggle.

### Time-policy experiment

`codex/time-policy` adds `notebooks/kaggle_time_policy.ipynb` and
`docs/TIME_POLICY.md`. Both sides use one pinned engine commit, SEE disabled;
only NextIterationPct differs (new=100, old=150). Integer overrides are limited
to the advertised 50..500 range; all other fixed protocol settings stay protected.
The existing validator supports `--experiment time-policy`: full Kaggle tests,
untimed reference/control/candidate equivalence, then alternating timed diagnostics
(100/150, 150/100), before the single 100-game match at 100 ms.
No engine defaults or draw rules change. `validation/*.json` adds attempted_depth,
search_time_ms, mate, next_iteration_pct and movetime_ms for diagnostic rows.
These are measurements only; the notebook makes no strength decision.

### TT usage diagnostics

`codex/tt-diagnostics` adds `tools/tt_stats.py`, `tools/tt_diagnostics.py`,
`notebooks/kaggle_tt_diagnostics.ipynb` and `docs/TT_DIAGNOSTICS.md`.
Engine files and TT policy stay unchanged. A tools-only Searcher subclass
counts interior TT probes/context/depth/cutoff/store/clear events.
`data/tt/<id>/` records immutable inputs, protocol, full Kaggle test log,
per-recorded-game JSON, checkpoint hashes and aggregate factual results.
Both ordinary and diagnostic searches replay the control positions of the
saved 100-game time-policy experiment, with equal recorded node budgets and
persistent per-game tables. Every search result, board and table must agree.
This is not a new match, timed speed test or strength measurement. Root's
direct move-hint lookup is outside the probe denominator; mismatch reasons overlap.
Local smoke tests may use direct table/protocol fixtures only. Never run
`test_tt_stats_search` or the replay CLI locally. Analysis goes in `analysis/`.

### TT context-pair experiment

`codex/tt-two-contexts` adds opt-in TTTwoContexts (default false), preserving
exact draw context/depth/bound checks and the same total entry capacity.
`notebooks/kaggle_tt_two_contexts.ipynb` runs full Kaggle correctness tests,
repeated uninstrumented benchmarks and two deterministic 20-game frozen
replays before conditionally running one 100-game match at 100 ms.
SEE stays off and NextIterationPct=150. `tools/tt_pair_experiment.py` records
cost/retention eligibility only, never a strength/merge decision. No second-slot
cutoffs, increased fixed-depth nodes or >10% median slowdown skips new matches.
TT diagnostics gain optional second_slot_* / context_evictions counters;
historical diagnostic summaries remain readable with absent fields as zero.
Root direct hints remain outside the probe denominator. See docs/TT_TWO_CONTEXTS.md.

### `data/index.csv` fields

One row per run: `run_name,date,engine_version,opponent,games,score_pct,elo_diff,sprt_decision`.
