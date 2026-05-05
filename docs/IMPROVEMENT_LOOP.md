# Prover improvement loop

How to iterate on a DQBF prover without fooling yourself. This was
written before `frust` existed; the "Lessons" section below is what we
learned from actually running ~35 iterations on it.

```
generate (EQFOB/AIGER/TLSF)  →  train families  →  run prover  →  verify each result
        ↑                                                              │
        └──────────── per-instance diff vs baseline, propose change ───┘
```

## Current state (2026-05)

| Area | Status |
|---|---|
| `tools/verify` SAT (DQDIMACS+AIGER → CNF, kissat) | working |
| `tools/verify` UNSAT (`.frp` replay) | working |
| `frust` | 1077/1517 train, 728 verified certs, 0 invalid; CDCL+expand+saturate interleaved |
| `forkres` (Python reference) | 131/1517; correctness oracle, not speed |
| Multi-solver runner + report (cactus, pairwise, cert table) | working |
| Benchmark families | 27 train, 4 valid; 3 domains (DQBF/HWMC/SYNTCOMP) |
| External solvers wired | dqbdd, hqs, pedant, caqe, cadet, abc-bmc/-pdr, strix |
| HISTORY.md | per-iteration narrative for `frust` |

## Benchmark split — policy

Unchanged: `train/` (loop iterates here), `valid/` (seed-shifted spot
check), `test/` (competition sets, evaluation only). Never feed `test/`
results into a heuristic decision.

## The loop itself

1. **Probe** — `scripts/frust_opt_loop.py`: full `train/` set, 10s, j=48,
   every cert through `tools/verify`. Output: solved/total, INVALID
   count, missing-cert count, slowest-small-instance list, **per-instance
   diff vs the previous run**.
2. **Hypothesise** — pick the smallest unsolved instance (by vars × time);
   `--debug-expand` it; state what you think is the bottleneck.
3. **Change** — one commit. `cargo test` + tiny-5 cert verify before
   probing.
4. **Probe again.** Any INVALID → revert immediately. Regression diff
   tells you *which* instances flipped, not just how many.
5. **Record** in `HISTORY.md`: bottleneck, observation, change, result.
6. Periodically: 9-solver `dqbf-bench multi` for the cactus + cross-tool
   disagreement check.

---

## Lessons from running the loop

What ~35 frust iterations taught us about the *loop*, not the solver.
These are the things that, in hindsight, would have saved the most
iterations.

### Probe the full train set from iteration 0

Iters 0-17 used a 344-instance subset. Widening to 804 at iter 18
immediately surfaced `dep_cycle_n1` (11 variables — the paper's own
counterexample) and a 74s-on-3s-timeout bug. Both were sitting there
the whole time. The cost of probing 1500 instances at j=48 is ~5
minutes; the cost of missing a bug for 18 iterations is days.

### Per-instance regression diff, not just counts

Iters 10, 13, 19, 20, 21, 25 each *lost* instances. The count drop
told you something broke; the diff (`+ these / − those`) told you
*why*. Once added, every "lost 3 instances" became immediately
explainable instead of guesswork tuning. The diff is now in the probe
output by default.

### Never rebuild the binary while a benchmark is running

Three runs were contaminated this way (the multi-solver bench takes
~10 minutes; `cargo build` mid-run swaps the binary under it). Either
use a copied binary path for the bench, or — simpler — don't start
editing until the bench task notifies done.

### Read the relevant paper before reimplementing

Iters 8-13 groped toward what CAQE/iDQ already describe. The slot-DPLL
at iter 16 *is* their abstraction-refinement loop. Reading those papers
carefully at iter 4 (when ∀-expansion was introduced) would have saved
roughly half the round-2 iterations.

### Stricter cert checking from the start

The `"VALID" in "INVALID"` substring bug (iter 5) and the
"ever-decided" soundness bug (iter 13) both slipped because the probe
used grep-style checks. The tiny `fork_unsat` instance that exposed
iter 13 should have been a unit test for `expand` from the moment
expand was written. **Rule**: every soundness-critical code path gets a
hand-built tiny instance in `tests/integration/tiny/`.

### Verify your worked examples with the brute-force oracle

The first DQBF-BCE example I wrote was wrong (claimed UNSAT, actually
SAT). `core.semantics.is_true` exists exactly for this — three lines
of Python, settles it. Any worked example in a `.md` file should have
been checked.

### Fixed time-budgets create cactus shelves

The 1-second saturation window after expand-UNSAT made ~180 instances
finish at exactly ~1s — a visible flat shelf in the cactus. Adaptive
budgets (proportional to time-spent-so-far, geometrically growing
slices) give a continuous curve and don't penalise the easy cases.

### A `--debug` flag for the search core

Rebuilt-with-eprintln a dozen times to see slot counts, which strategy
fired, where it bailed. A structured `--debug-expand` dump halved each
"examine" step once added.

### Two soundness gates, not one

Per-iteration: tiny-5 verify + INVALID count in the probe. Per-batch:
cross-solver disagreement check (`dqbf-bench multi` with hqs/pedant).
The second one catches unsound UNSAT-without-proof verdicts that the
first can't. The runner cert-path collision bug (`bmc_circuits/` vs
`bmc_circuits_succinct/` shared stems) was caught by the per-batch
check showing both frust *and* pedant with INVALID certs — which
pointed at the runner, not either solver.

### Preprocessing as a one-shot stage is a smell

BCE was a one-shot upfront pass for 8 iterations before being pulled
into the scheduler loop. Any "do X once at the start" step should be
asked: would re-running X after the solver makes progress change
anything? Usually yes.

### Track where the next architecture change is, separately from tuning

Iters 6-10 and 19-20 were spent tuning constants (conflict caps, slice
budgets) when the actual blocker was architectural (CDCL, resumable
expand). A "Next" section in CLAUDE.md naming the *structural* change
keeps tuning from filling the iteration budget.

## Gate (unchanged)

Accept a change iff: zero INVALID certs, zero ok→{wrong,error}
regressions in the diff, net Δsolved ≥ 0. A speed-only change (same
solved, faster) is fine if it doesn't add code complexity you'll regret.
