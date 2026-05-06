# Prover improvement loop

How to iterate on a DQBF prover without fooling yourself. This was
written before `frust` existed; the "Lessons" section below is what we
learned from actually running ~35 iterations on it.

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

2. **Hypothesise** — this is where most of the leverage is; spend real
   effort here.

   Sample ~10 instances that are either unsolved or taking non-trivial
   time (>1s). Don't fixate on the single smallest one. `--debug-expand`
   / `perf record` / dump intermediate state on each, and look for
   **commonalities**: same family? same |U| range? same phase bailing?
   same clause-count blowup?

   Then ask what the *fundamental constraint* is. Name it at the right
   level:
   - **implementation roughness** — a hot loop allocating, a linear scan
     where an index would do (perf shows it directly);
   - **algorithmic limitation** — the algorithm is the right one but
     this instance shape defeats its heuristic (e.g., model drift
     inflating slot counts);
   - **architectural limitation** — the phase structure itself is
     wrong (e.g., expand can prove UNSAT but can't emit a `.frp`, so
     the verdict is held back for saturation);
   - **research-approach limitation** — no known technique handles this
     shape well (e.g., `dep_cycle` without SFEx).

   You may need to **build a tool** to see what's happening (a
   `--debug-X` flag, a one-off script that tabulates a quantity across
   the sample) or **test the hypothesis at small scale** (hand-craft a
   3-variable instance with the same shape, check the brute-force
   oracle, watch the solver step through it). A hypothesis you can't
   demonstrate on a tiny instance is probably wrong.

3. **Change** — one commit when the change is local; **several commits
   when it's architectural**. The big wins (CDCL, expand-UNSAT,
   resumable scheduler) each took 3-5 commits with intermediate states
   that didn't fully work. That's fine — `cargo test` + tiny-5 cert
   verify after each commit keeps the soundness invariant; the probe
   only needs to run on the last one.

4. **Probe again — and test the intended effect specifically.** This
   step usually takes several attempts.

   - Any INVALID → fix or revert before going further.
   - Regression diff tells you *which* instances flipped, not just how
     many.
   - **Check the change did what you hypothesised**, not just that the
     count went up. If the hypothesis was "fixpoint converges in ≤4×rows
     steps", confirm it on the sample with `--debug-expand`. If it was
     "cert size shrinks", check a cert. A change that gains +5 for the
     wrong reason will regress later.
   - Expect to iterate within this step: the first implementation often
     has a subtle bug (an INVALID cert from a missing validation pass,
     a counter that doesn't reset, a `≥` that should be `>`). Tighten,
     re-probe, repeat until the result is both correct *and* explained.

5. **Record** in `HISTORY.md`: the sampled instances, the constraint
   you identified, what you tried (including the dead ends), what
   stuck, and the result. Also record **gotchas, papercuts, and
   inconsistencies** you hit along the way — a `cargo fmt` that
   reordered something, a probe-script edge case, a debug print that
   misled you. Those notes save the next iteration from re-discovering
   them.

6. **Regenerate the report.** After each batch (or any architectural
   change), run the multi-solver benchmark and archive the HTML:

   ```sh
   rm -rf results/
   python -m benchmarks.runner.cli multi --root benchmarks/train \
     --solvers frust,dqbdd,pedant,hqs --timeout 10 -j 48 \
     -o results/train.jsonl --report results/train.html \
     --certdir results/certs --verify-certs
   cp results/train.html "docs/dev_reports/$(date +%Y-%m-%d_%H%M)_<slug>.html"
   python -c "from scripts.make_report import write_index; write_index()"
   git add docs/dev_reports && git commit -m "<slug> report"
   ```

   The cactus shows whether the *shape* changed (shelves, phase
   boundaries); the cert table catches anything the per-iter probe
   missed; the disagreement section is the second soundness gate.
   Don't edit the solver while this runs — contaminated reports have
   bitten us three times.

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

### Result cache makes re-baselining cheap — never clear it

`dqbf-bench multi` caches results under `results/.bench_cache/` keyed
on `sha256(binary-bytes, instance-content, timeout)`. **Do not `rm -rf`
the cache** — keys are content-addressed, so a rebuilt binary or
regenerated instance is a *new* key; old entries are unreferenced, not
stale. If a cached result looks wrong, the bug was in that binary (and
that hash never recurs). After a frust rebuild only the frust column
re-runs; the rest hits the cache. To compare frust versions, register
each tagged binary in `solvers.py` (e.g. `frust-v1.20`, `frust-v2.0`).
`--no-cache` forces a fresh run; `backfill()` seeds from an existing
JSONL.

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
`bmc_circuits/succinct/` shared stems) was caught by the per-batch
check showing both frust *and* pedant with INVALID certs — which
pointed at the runner, not either solver.

### Preprocessing as a one-shot stage is a smell

BCE was a one-shot upfront pass for 8 iterations before being pulled
into the scheduler loop. Any "do X once at the start" step should be
asked: would re-running X after the solver makes progress change
anything? Usually yes.

### Architecture changes make bigger jumps than tuning constants

The iteration record is unambiguous on this: ∀-expansion (+18),
slot-DPLL (+9), CDCL (+4), expand-UNSAT verdict (+160), outer-CEGAR
(+15), BCE (+14). Every constant-tuning iteration was ±0-3. Iters 6-10
and 19-20 were spent on conflict caps and slice budgets when the actual
blocker was architectural. A "Next" section in CLAUDE.md naming the
*structural* change keeps tuning from filling the iteration budget. If
you find yourself adjusting a number for the third time, the number is
not the problem.

## Gate

The hard line is **zero INVALID certs** — that never bends.

Beyond that, accept a change when it's a net improvement *in
expectation*, not strictly Δsolved ≥ 0. Losing a handful of instances
is fine when:
- the gains elsewhere are substantially larger (option 3b: −6 on
  `random_bv` for a continuous architecture), or
- the change deletes code (simplification round: −515 LoC, +2 solved),
  or
- the lost instances are borderline-timing noise (±1 at j=48 is noise).

What you *do* want to understand is *which* instances were lost and
why — the per-instance diff makes that cheap. A loss you can explain
("the ported outer-CEGAR is missing min-change re-pick") is a TODO; a
loss you can't is a bug.
