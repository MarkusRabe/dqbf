# benchmarks/train/cbmc/ — C-program BMC via CBMC

Small C functions with `__CPROVER_assert`/`__CPROVER_assume`, run
through `cbmc --dimacs` at several unwind depths. The output is
propositional (no universals) — the degenerate DQBF case — but with
realistic program-verification CNF structure (carry chains, ITE
cascades, array selects).

Convention: CBMC's CNF is **SAT iff the assertion can fail** at that
unwind, so `expected="sat"` ⇔ buggy program, `expected="unsat"` ⇔
safe program.

| Scale param | What it sweeps |
|---|---|
| `unwind` (5, 20) | loop bound for BMC |

To regenerate (needs `cbmc` on PATH):

```sh
python -m benchmarks.train.cbmc.generate
```

The runner can register `cbmc` itself as a `domain="cbmc"` cross-check
solver (consumes the source `.c`, not the `.dqdimacs`) — same pattern
as abc for HWMC and strix for SYNTCOMP.
