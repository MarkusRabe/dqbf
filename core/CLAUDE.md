# core/

The shared IR and ground-truth machinery. Everything else either
produces or consumes a `core.Formula`.

```
formula.py      Formula(n_vars, universals, dependencies, clauses) + dep helpers
dqdimacs.py     parse/load/dump/dumps; handles .gz
semantics.py    brute-force is_true / find_skolem — the oracle for tests
certificate.py  Skolem ↔ JSON
aiger.py        minimal .aag writer (Shannon expansion of a Skolem table)
```

`semantics.py` is exponential and exists solely to give the test suite a
ground truth on instances small enough to enumerate. Do not call it from
production code paths.
