# Tests

Install the tools dependencies, then run the complete correctness suite from the repository root:

```powershell
python -m pip install -r requirements-tools.txt
python -m unittest discover -s tests -v
```

`test_uci.py` covers the UCI session and `test_stats.py` the Elo/SPRT helpers.
`test_perft.py` checks the reference move-tree counts. `test_board.py` covers FEN,
hashing, reversible moves, special moves, repetition, and draw rules. The engine
core uses only the standard library; the full suite also exercises tools that
use python-chess and NumPy. `test_baseline.py` checks reference provenance,
failure retention, immutability and benchmark comparison boundaries.

Kaggle reference collection and result publishing: [docs/BASELINE.md](../docs/BASELINE.md).

`test_uci_async.py` covers worker cancellation and real CLI pipes: finite searches
must answer `isready`, accept `stop`, publish natural completion without more
input, and avoid duplicate `bestmove` responses. Position/option/new-game/quit
cancellation and EOF cleanup are also covered. Run the full suite in Kaggle;
the pipe regressions are bounded and do not run matches or Stockfish.

`test_tt_context.py` separates small, search-free context checks from real search
regressions. Kaggle runs the original clock-0/clock-98 warm-table example and
both directions of a controlled legal cycle whose descendant becomes a third
repetition only with prior history. The oracle has TT disabled, and null-move/LMR
are disabled in these comparisons to isolate cache correctness.

`test_uci_configuration.py` checks per-session evaluation settings, immediate TT
invalidation, rejected spin values, same-value reuse and legacy evaluator compatibility.
Its short configuration tests stub the root where needed; the separate search
regression class belongs to Kaggle. Real regressions compare toggled passed-pawn
and bishop-pair scores with clean sessions, and explicit/legacy flag changes with
a TT-disabled oracle. A mocked worker test also checks that an Eval option is not
mutated until the previous worker has stopped.

`test_analysis_configuration.py` checks content-based identities, immutable config
guards, legacy read compatibility, warm/corrupt/foreign caches, part identity and
CLI resume using mocked evaluation only. `test_match_metadata.BookMetadataTests`
checks advertised book defaults and case-insensitive last overrides without matches.
The existing fake-UCI analysis pipeline test also seals tagged parts in Kaggle.

`test_endgame_rules.py` separates small position/oracle and mocked terminal-flow
checks from actual search regressions. Kaggle checks horizon stalemate under
multiple alpha-beta windows, mate/stalemate at MAX_PLY, ordinary quiet positions,
and rook underpromotion with cold/warm/disabled TT for both colours. In
`8/k1P5/2K5/8/8/8/8/8 w - - 0 1`, c8=Q is stalemate while c8=R continues;
quiescence must see the rook, and a depth-1 root search must select it.
Tactical generation is compared with python-chess captures plus all four
promotions, including captures, en passant and its pinned illegal case.
No real searches or match runs are needed on the user's PC.
