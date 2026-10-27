# Tests

Run the complete Stage 1 correctness suite from the repository root:

```powershell
python -m unittest discover -v
```

`test_uci.py` covers the UCI session and `test_stats.py` the Elo/SPRT helpers.
`test_perft.py` checks the reference move-tree counts. `test_board.py` covers FEN,
hashing, reversible moves, special moves, repetition, and draw rules. No external
Python package is needed.
