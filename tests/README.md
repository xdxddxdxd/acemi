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
