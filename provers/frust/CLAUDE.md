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
(full train set, 10s, j=32); it prints a per-instance regression
diff so any flip from solved→unknown is visible.

**Keep `HISTORY.md` up-to-date.** After each batch of iterations or
architectural change, append a paragraph in the same style (anchor on
the bottleneck instance, what was tried, what stuck, with numbers and
the commit hash). The iteration table at the end of HISTORY.md is the
quick-reference; the prose is the actual record.

**Version with each iteration.** Tag `frust-vM.N` where `M` is the
architectural era (1 = pre-definability, 2 = definability+arbiters+
interpolation+`.frp`) and `N` tracks the iteration count within that
era (e.g. `v2.40`, `v2.41`, …). Bump `M` only at a genuine
architectural break that changes the module map. After each iteration
that lands (probe+commit+push), retag: `git tag -f frust-vM.N HEAD &&
git push -f origin frust-vM.N`. Register the binary in
`benchmarks/runner/solvers.py` only at report milestones.

**Reports cover all four domains.** The multi-solver report compares
DQBF solvers on the full train set, but the report's domain selector
also splits out QBF (`cadet`, `caqe`, `rareqs`), HWMC (`abc-bmc`,
`abc-pdr`), and SYNTCOMP (`strix`) on their format-compatible
subsets. Pass all of them to `--solvers` so each tab is populated:

```sh
dqbf-bench multi --root benchmarks/train \
  --solvers frust-vM.N,dqbdd,pedant,hqs,cadet,caqe,rareqs,abc-bmc,abc-pdr,strix \
  -j 32 --timeout 10 -o results/train.jsonl --report results/train.html \
  --certdir results/certs --verify-certs
```

The result cache makes re-running unchanged solvers free, so the cost
is the same as a frust-only run.

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

## Goals (set 2026-05-09)

The improvement loop's gate is still "0 INVALID, net-positive in
expectation, architecture > tuning." Beyond that, the *direction* is:

1. **Solve the most problems by a significant margin** — not just
   ahead of the second-best sound solver, but clearly ahead of every
   solver including dqbdd. Closing the gap to dqbdd's BDD expansion
   without dependency schemes is the central research question.
2. **Verify all outputs** — every SAT verdict has a checked `.aag`,
   every UNSAT verdict has a checked `.frp`. The remaining no-cert
   verdicts (~700) are arbsolve-exhausted UNSAT on large succinct
   instances; closing them needs the FEx-chain emission (Phase 3b) or
   ext-rule support in the verifier.
3. **Limit special cases; find unifying algorithmic principles.** The
   solver has accumulated five expand modes (`Definability`, `Partial`,
   `OuterCegar`, `SlotDpll`, `Exhausted`), each with sub-strategies.
   When two modes do similar things on different instance shapes, look
   for the algorithm that subsumes both. The CEGAR/CEGIS/interpolation
   loop is the unifying frame — extend it to cover what `Partial` and
   `SlotDpll` do, then delete them. Fewer paths = fewer soundness
   pitfalls = faster iteration.

## Research walls (named in HISTORY, don't bash without a new angle)

- `dep_cycle` n≥4 — journal §6 proof is exponential without dep
  schemes (off-limits); pedant also UNKNOWN.
- `bmc_circuits/succinct` large instances — closed cyclic gate-DAG
  with 0 Padoa roots; arbsolve over thousands of free cells doesn't
  converge.
- `collatz/tonly` — pedant also UNKNOWN.
