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

Phased; each phase is green before the next starts.

1. **Python core.** `formula.py` (DQDIMACS parse + round-trip print
   tests), `clause.py`, `rules.py` (Res / ∀Red / FEx / SFEx as pure
   functions, property-tested for soundness + annotation invariants),
   naive saturation `search.py`. Pass the hand-sized SAT/UNSAT set in
   `tests/integration/tiny/`.
2. **Certificate extraction.** Track per-clause provenance during search;
   on SAT, synthesize Skolem AIGs via py-aiger; round-trip every result
   through `tools/verify/`.
3. **Refutation trace.** Line-based `.frp` proof format; independent
   replayer in `tools/verify/` reusing `rules.py`.
4. **Rust port** (only once 1–3 are stable):
   - [ ] `rust/dqdimacs/` crate; fuzz against the Python parser.
   - [ ] Port `rules.py` 1:1; proptest each rule against the Python
         reference via a JSON fixture corpus (or PyO3).
   - [ ] Search loop with watched-literal clause DB.
   - [ ] Wire into `benchmarks/runner/`;
         `tests/integration/diff_provers.py` enforces parity.
   - [ ] Profile on `benchmarks/dqbf/qbfeval/`; optimize hot paths
         (lift `forbid(unsafe_code)` only where profiling justifies it).
5. **Heuristics.** Variable / clause selection, dependency-aware
   ordering, restart schedule. Gated behind flags; **off by default** in
   the Python reference so it stays a clean oracle.
