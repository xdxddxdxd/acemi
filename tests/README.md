# Tests

Run the complete Stage 1 correctness suite from the repository root:

```powershell
python -m unittest discover -v
```

`test_perft.py` checks the reference move-tree counts. `test_board.py` covers FEN,
hashing, reversible moves, special moves, repetition, and draw rules. No external
Python package is needed.
