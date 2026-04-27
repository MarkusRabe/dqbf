# provers/python/ — reference fork-resolution prover

Correctness-first. This is the executable specification of the proof
system; the Rust prover and the certificate verifier are checked against
it.

## Module layout (planned)

```
forkres/
  formula.py     DQDIMACS parser → Formula(universals, existentials: {var: deps}, clauses)
  clause.py      annotated clause = literals + per-literal annotation (fork copy index)
  rules.py       resolve(c1, c2, pivot), fork(c, uvar), merge(c) — each pure, each unit-tested
  search.py      proof search loop (saturation / CDCL-style; pluggable strategy)
  certificate.py Skolem-function extraction → py-aiger AIG
  proof.py       refutation trace emit + replay
  cli.py         argparse entry point honoring the shared contract in ../CLAUDE.md
```

## Conventions

- Everything in `rules.py` is a **pure function** of immutable inputs.
  Mutation lives in `search.py` only.
- No I/O outside `formula.py` (parse) and `cli.py` (drive).
- Type-annotated; `mypy --strict` clean.

## References

- Proof rules: `../../OVERVIEW.md` §"The proof system".
- DQDIMACS: header `p cnf N M`, then `a ... 0` / `e ... 0` / `d v d1 d2 ... 0`
  lines, then clauses. See `../../docs/references/dqdimacs.md`.
- AIGER: https://fmv.jku.at/aiger/FORMAT — use `py-aiger`.

## Plan

- [ ] `formula.py` + round-trip parse/print tests.
- [ ] `rules.py` with property tests (resolution soundness, fork
      annotation invariants).
- [ ] Naive saturation search; pass the hand-sized SAT/UNSAT set in
      `tests/integration/tiny/`.
- [ ] Certificate extraction; every SAT result verified by
      `tools/verify/`.
- [ ] Refutation trace + independent checker.
