# provers/frust/ — standalone Rust DQBF solver

Single-threaded fork-resolution solver. **No code shared** with the
rest of the repo: own DQDIMACS parser, own rule implementations, own
`.frp`/`.aag` writers. The Python verifier in `tools/verify/` is the
correctness oracle — every certificate is checked.

## Build & run

```sh
cargo build --release --manifest-path provers/frust/Cargo.toml
provers/frust/target/release/frust FILE.dqdimacs[.gz] --timeout 10 \
  --cert out.aag --proof out.frp [--debug-expand]
```

Exit codes 10/20/0 (sat/unsat/unknown). `--debug-expand` dumps slot
counts, which strategy fired, and where expand bailed.

## Current architecture

See [`FRUST_v1.0.md`](FRUST_v1.0.md) for the v1.0 module map and the
two-phase (expand → saturate) design. Since v1.0: `bce.rs` runs once
up front and feeds both engines; `expand.rs` gained outer-∃ CEGAR for
the ∃∀∃ shape and an iterative-deepening partial scan for |U|>16;
`search.rs::solve` is being restructured as an interleaved scheduler
(expand and saturate slices share a single CDCL with cross-feed of
short derived clauses).

## Optimization loop

See [`../../docs/IMPROVEMENT_LOOP.md`](../../docs/IMPROVEMENT_LOOP.md)
for the methodology and the lessons learned from running it.

Each iteration: state hypothesis → implement → `cargo test --release`
→ tiny-5 cert verification → probe → record. **Any INVALID cert
reverts immediately.** The probe is `scripts/frust_opt_loop.py`
(full train set, 10s, j=48); it now prints a per-instance regression
diff so any flip from solved→unknown is visible.

**Keep `HISTORY.md` up-to-date.** After each batch of iterations or
architectural change, append a paragraph in the same style (anchor on
the bottleneck instance, what was tried, what stuck, with numbers and
the commit hash). The iteration table at the end of HISTORY.md is the
quick-reference; the prose is the actual record.

```sh
for f in tests/integration/tiny/*.dqdimacs; do rm -f /tmp/c.aag /tmp/p.frp; \
  provers/frust/target/release/frust "$f" --cert /tmp/c.aag --proof /tmp/p.frp >/dev/null 2>&1; rc=$?; \
  echo -n "$(basename $f): rc=$rc "; \
  if [ $rc -eq 10 ]; then python -m tools.verify.cli sat "$f" /tmp/c.aag -o /tmp/v.cnf --solve 2>&1|grep -E '^VALID|INVALID'; \
  elif [ $rc -eq 20 ]; then [ -f /tmp/p.frp ] && python -m tools.verify.cli unsat "$f" /tmp/p.frp 2>&1|grep -E '^VALID|INVALID' || echo "(no proof)"; \
  else echo; fi; done
```

## Docs

- [`HISTORY.md`](HISTORY.md) — **read this first.** Full development
  narrative with the iteration table; explains why each piece exists.
- [`../../docs/IMPROVEMENT_LOOP.md`](../../docs/IMPROVEMENT_LOOP.md) —
  the loop methodology and what running it taught us.
- [`FRUST_v1.0.md`](FRUST_v1.0.md) — architecture snapshot at the
  v1.0 commit.
- [`BCE.md`](BCE.md) — DQBF-BCE soundness, reconstruction, fire rate.

## Next

- `bmc_circuits_succinct` (145/150 unsolved): frame-index universals
  with mixed-dep existentials. Needs frame-aware expansion.
- `dep_cycle`: better SFEx partition heuristic.
- CDCL proof tracing — turn the iter-28 expand-UNSAT verdicts into
  verified `.frp`.
