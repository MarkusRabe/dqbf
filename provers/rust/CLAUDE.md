# provers/rust/ — performance fork-resolution prover

Same algorithm and CLI contract as `../python/`, optimized for the
benchmark runner. Do not start here; port from a green Python reference.

## Layout (planned)

```
Cargo.toml          workspace
crates/
  dqdimacs/         parser (zero-copy where possible)
  forkres-core/     clause DB, watched literals, proof rules
  forkres-cli/      binary: same flags/exit codes as python prover
```

## Conventions

- `#![forbid(unsafe_code)]` until profiling proves a hotspot needs it.
- Determinism: fixed iteration order (IndexMap / sorted), `--seed` plumbs
  into every RNG.
- Feature parity is tested by
  `tests/integration/diff_provers.py` — same input → same SAT/UNSAT and
  (mod variable renaming) same certificate.

## References

- `../python/forkres/` is the spec.
- AIGER writer: vendor a tiny ASCII-`.aag` emitter rather than binding
  libaiger; keep the binary format for a later pass.

## Plan

- [ ] `dqdimacs` crate + fuzz against the Python parser.
- [ ] Port `rules.py` 1:1; proptest each rule against the Python
      reference via PyO3 or a JSON fixture corpus.
- [ ] Search loop with watched-literal clause DB.
- [ ] Wire into `benchmarks/runner/`.
- [ ] Profile on `benchmarks/dqbf/pec/`; optimize hot paths.
