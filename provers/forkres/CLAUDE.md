# provers/forkres/ — fork-resolution prover

Decide truth of a DQBF via (Strong) Fork Resolution and, on **true**
instances, emit Skolem functions as an AIGER circuit. See
`../../OVERVIEW.md` for the proof system.

This directory holds **both** the Python reference and (later) a Rust
implementation. They share the CLI contract in `../CLAUDE.md`.

## Layout

```
forkres/
  rules.py        resolve, universal_reduce, fork_extend, strong_fork_extend — pure
  rules_test.py
  search.py       naive saturation + bounded FEx/SFEx; emits Proof on UNSAT,
                  Skolem (via core.semantics.find_skolem) on SAT
  search_test.py
  cli.py          entry point honoring ../CLAUDE.md contract
  smoke_test.py
  rust/           Rust crate(s): same algorithm, optimized data structures
    Cargo.toml    workspace
    dqdimacs/     parser (ported, tested)
    forkres-core/ stub (returns Unknown)
    forkres-cli/  binary; same flags/exit codes
```

Parsing and the IR live in `core/`, not here.

## Conventions

- **Python is the spec.** Everything in `rules.py` is a pure function of
  immutable inputs; mutation lives in `search.py` only. No I/O outside
  `cli.py`.
- `mypy --strict` clean.
- **Rust mirrors Python.** `#![forbid(unsafe_code)]` until profiling
  proves a hotspot needs it; fixed iteration order.

## References

- Proof rules: `../../OVERVIEW.md` §"The proof system" and
  `../../docs/references/fork_resolution_journal/main.tex`
  (`thm:strongsoundandcomplete`, `lem:elimstrongforks`).
- DQDIMACS: `../../docs/references/dqdimacs.md`.
- AIGER: https://fmv.jku.at/aiger/FORMAT — writer is `core/aiger.py`.

## Plan

Phased; each phase is green before the next starts.

1. ✅ **Python core.** `rules.py` (Res / ∀Red / FEx / SFEx as pure
   functions, property-tested for soundness), naive saturation
   `search.py`. Pass the hand-sized SAT/UNSAT set in
   `tests/integration/tiny/`.
2. **Certificate extraction.** Track per-clause provenance during search;
   on SAT, synthesize Skolem AIGs via `core/aiger.py`; round-trip every
   result through `tools/verify/`. (Currently: brute-force `find_skolem`;
   the saturation-based extraction is the open work — see P2 in
   `docs/IMPROVEMENT_LOOP.md`.)
3. ✅ **Refutation trace.** `.frp` proof format; the independent replayer
   in `tools/verify/unsat.py` re-implements the rule checks locally
   (it shares no code with this directory).
4. **Rust port** (only once 1–3 are stable):
   - [x] `rust/dqdimacs/` crate; fuzz against the Python parser.
   - [ ] Port `rules.py` 1:1; proptest each rule against the Python
         reference via a JSON fixture corpus (or PyO3).
   - [ ] Search loop with watched-literal clause DB.
   - [ ] Wire into `benchmarks/runner/solvers.py`.
   - [ ] Profile on `benchmarks/test/dqbf_qbflib/`; optimize hot paths
         (lift `forbid(unsafe_code)` only where profiling justifies it).
5. **Heuristics.** Variable / clause selection, dependency-aware
   ordering, restart schedule. Gated behind flags; **off by default** in
   the Python reference so it stays a clean oracle.
