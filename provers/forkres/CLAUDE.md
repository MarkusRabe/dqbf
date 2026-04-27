# provers/forkres/ — fork-resolution prover

Decide truth of a DQBF via (Strong) Fork Resolution and, on **true**
instances, emit Skolem functions as an AIGER circuit. See
`../../OVERVIEW.md` for the proof system.

This directory holds **both** the Python reference and (later) a Rust
implementation. They share test fixtures and the CLI contract in
`../CLAUDE.md`; the Rust build is differentially tested against the
Python one.

## Layout

```
forkres/
  formula.py        DQDIMACS parser → Formula(universals, existentials: {var: deps}, clauses)
  formula_test.py
  clause.py         annotated clause = literals + per-literal annotation (fork copy index)
  rules.py          resolve(c1,c2,pivot), fork(c,uvar), strong_fork(c,uvar,C3), reduce(c)
  rules_test.py
  search.py         proof search loop (saturation / CDCL-style; pluggable strategy)
  certificate.py    Skolem-function extraction → py-aiger AIG
  proof.py          refutation trace emit + replay
  cli.py            entry point honoring ../CLAUDE.md contract
  rust/             Rust crate(s): same algorithm, optimized data structures
    Cargo.toml      workspace
    dqdimacs/       parser
    forkres-core/   clause DB, watched literals, proof rules
    forkres-cli/    binary; same flags/exit codes
```

## Conventions

- **Python is the spec.** Everything in `rules.py` is a pure function of
  immutable inputs; mutation lives in `search.py` only. No I/O outside
  `formula.py` (parse) and `cli.py`.
- `mypy --strict` clean.
- **Rust mirrors Python.** `#![forbid(unsafe_code)]` until profiling
  proves a hotspot needs it; fixed iteration order; `--seed` plumbs into
  every RNG. Feature parity is enforced by
  `tests/integration/diff_provers.py`.

## References

- Proof rules: `../../OVERVIEW.md` §"The proof system" and
  `../../docs/references/fork_resolution_journal/main.tex`
  (`thm:strongsoundandcomplete`, `lem:elimstrongforks`).
- DQDIMACS: `../../docs/references/dqdimacs.md`.
- AIGER: https://fmv.jku.at/aiger/FORMAT — use `py-aiger`.

## Plan

- [ ] `formula.py` + round-trip parse/print tests.
- [ ] `rules.py` with property tests (resolution soundness, fork
      annotation invariants).
- [ ] Naive saturation search; pass `tests/integration/tiny/`.
- [ ] Certificate extraction; every SAT result verified by
      `tools/verify/`.
- [ ] Refutation trace + independent checker.
- [ ] Rust port: `dqdimacs` crate fuzzed against the Python parser, then
      `rules.py` ported 1:1 with proptest fixtures, then search loop with
      watched literals; wire into `benchmarks/runner/`.
