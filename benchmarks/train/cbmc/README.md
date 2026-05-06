# benchmarks/train/cbmc/ — C-program verification, four encodings

Consolidated family (supersedes the old `cbmc_v2/` split). Two corpora,
four encodings:

- **handwritten** — small static `.c` functions under `sources/` with
  `__CPROVER_assert`/`__CPROVER_assume`, run through `cbmc --dimacs`.
  Propositional (all-∃). Ground truth = cbmc's own verdict.
- **flat / succinct / indinv** — twelve single-loop algorithms
  (popcount, parity, bit-reverse, shift-add multiply, restoring
  division, subtractive GCD, streaming min, saturating counter, CLZ,
  Fibonacci, token bucket, one-hot roundtrip), each in `_ok` and
  `_bug` variants, swept over width `n∈{4,6,8}` × bound `k∈{8,16,32}`.

| dir | encoding | quantifier shape | semantics |
|---|---|---|---|
| `handwritten/` | `cbmc --dimacs` (static `.c`) | all-∃ | SAT ⇔ assert can fail |
| `flat/` | `cbmc --dimacs` (rendered `.c`) | all-∃ | SAT ⇔ assert can fail |
| `succinct/` | `seq_aig_for` → `encode_succinct` | ∀t,t' ∃ latch(t) — DQBF | SAT ⇔ assert can fail at bound k |
| `indinv/` | `seq_aig_for` → `encode_indinv` | ∀s,i,s' ∃ inv(s) — DQBF | **SAT ⇔ property holds** (invariant exists) |

flat and succinct are equisatisfiable per (family, variant, n, k) by
construction (the AIGER and the C source implement the same algorithm).
indinv is k-independent and dual: `_ok` → SAT, `_bug` → UNSAT.

The handwritten corpus has no transition extraction (CBMC's `--dimacs`
output carries no SSA names), so it only appears under `handwritten/`.

To regenerate:

```sh
python -m benchmarks.train.cbmc.generate            # all four
python -m benchmarks.train.cbmc.generate --mode succinct
```

The runner can register `cbmc` itself as a `domain="cbmc"` cross-check
solver (consumes the source `.c`, not the `.dqdimacs`).
