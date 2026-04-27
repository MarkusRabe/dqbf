# provers/

DQBF provers. **One directory per prover**, named for the
algorithm/approach — not for the implementation language. A prover
directory may contain Python, Rust, or both (e.g. a Python reference
with a Rust core bound via PyO3, or two independent implementations
sharing test fixtures).

```
provers/
  forkres/      Fork-resolution prover (this repo's primary)
    *.py        Python reference implementation — package `provers.forkres`
    *_test.py   colocated unit tests
    rust/       optional Rust implementation / acceleration crate
    CLAUDE.md
  <future provers go here as siblings>
```

## Shared CLI contract

Every prover exposes a CLI honoring:

```
stdin / file : DQDIMACS
stdout       : "SAT" | "UNSAT" | "UNKNOWN"
--cert PATH  : on SAT, write AIGER (.aag) Skolem functions
--proof PATH : on UNSAT, write a fork-resolution refutation trace
exit code    : 10 = SAT, 20 = UNSAT, 0 = UNKNOWN  (QBFEVAL convention)
```

and is byte-deterministic for a given input + `--seed`.

## References

- `../OVERVIEW.md` — proof system and literature.
- `../docs/references/fork_resolution_journal/main.tex` — authoritative
  rule definitions.

## Adding a new prover

1. `mkdir provers/<name>/` with `__init__.py`, `cli.py`, `CLAUDE.md`.
2. Register the CLI in `pyproject.toml` `[project.scripts]`.
3. Add it to `benchmarks/runner/` and `tests/integration/diff_provers.py`.
