# provers/

Fork-resolution-based DQBF provers.

## Purpose

Decide truth of a DQBF and, on **true** instances, emit Skolem functions
for every existential variable as an AIGER circuit. The proof system is
*fork resolution* — see `../OVERVIEW.md` for the inference rules and the
literature behind them.

Two implementations share one specification:

- `python/` — **reference**. Correctness is the only goal. Every proof
  rule is a small, individually unit-tested function. Used as the oracle
  for the Rust prover and for `tools/verify/`.
- `rust/` — **performance**. Same algorithm, optimized data structures,
  intended for the benchmark runner.

## Shared contract

```
stdin / file : DQDIMACS
stdout       : "SAT" | "UNSAT" | "UNKNOWN"
--cert PATH  : on SAT, write AIGER (.aag) Skolem functions
--proof PATH : on UNSAT, write a fork-resolution refutation trace
exit code    : 10 = SAT, 20 = UNSAT, 0 = UNKNOWN  (QBFEVAL convention)
```

Both provers must be byte-deterministic for a given input + `--seed`.

## References

- Rabe, *A resolution-style proof system for DQBF* — original + the
  unpublished journal revision at
  https://github.com/MarkusRabe/dqbf_fork_resolution_journal (fixes a
  soundness gap in the original proof; the revised rules are
  authoritative).
- `../OVERVIEW.md` — rule list and relationship to ∀Exp+Res / IR-calc.
- `../docs/references/` — cached PDFs / .tex of the above.

## Plan

1. **`python/forkres/` core** — clause DB, dependency map, the four proof
   rules (axiom, resolution, fork / universal-expansion, merge), proof
   search loop. Golden tests on hand-sized DQDIMACS.
2. **Certificate extraction** — track per-clause provenance during search;
   on SAT, synthesize Skolem AIGs via py-aiger; round-trip through
   `tools/verify/`.
3. **Refutation trace** — line-based proof format checkable by a tiny
   independent script in `tools/verify/`.
4. **Rust port** — once (1)–(3) are stable, port with the Python prover as
   a differential-testing oracle (`tests/integration/diff_provers.py`).
5. **Heuristics** — variable/clause selection, dependency-aware ordering;
   gated behind flags, off by default in the reference prover.
