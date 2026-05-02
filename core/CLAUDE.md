# core/

The shared IR and ground-truth machinery. Everything outside
`tools/verify/` either produces or consumes a `core.Formula`.

```
formula.py      Formula(n_vars, universals, dependencies, clauses) + dep helpers
dqdimacs.py     parse/load/dump/dumps; handles .gz
proof_trace.py  .frp Step/Proof dataclasses + JSON I/O (format only, no rule logic)
semantics.py    brute-force is_true / find_skolem / verify_skolem — the test oracle
certificate.py  Skolem ↔ JSON
aiger.py        minimal .aag reader+writer (parse_aag, Aag.cone_inputs, skolem_to_aag)
```

`semantics.py` is exponential and exists solely to give the test suite a
ground truth on instances small enough to enumerate. Do not call it from
production code paths.
