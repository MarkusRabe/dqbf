# Prover improvement loop

The medium-term goal is a closed loop in which the `forkres` prover is
iteratively improved against **scalable, generated** benchmark families,
with every result independently verified so the loop never has to trust
the prover.

```
generate (EQFOB)  →  train families  →  run prover  →  verify each result
        ↑                                                 │
        └─────────── compare vs baseline, propose change ─┘
```

## Current state (2026-04)

| Area | Status | Gap that blocks the loop |
|---|---|---|
| `core/` IR + DQDIMACS | working | — |
| `forkres` rules | working | SFEx exists but is never invoked by search |
| `forkres` search | partial | naive saturation; no heuristics; FEx only |
| SAT certificate | partial | obtained by brute-force `find_skolem`, not from the proof — caps at ~20 vars |
| `tools/verify` SAT | partial | enumerates 2^\|U\| universal assignments — caps at ~20 universals |
| `tools/verify` UNSAT | working | proof replay scales linearly |
| EQFOB compiler | working | `udiv urem`, signed cmp, variable shift unimplemented |
| EQFOB families | stub | `bitwidth_scaling/generate.py` emits source text only; never compiles to `.dqdimacs` |
| Runner | partial | runs + summarizes one JSONL; no two-run diff/regression |
| Encoders (qbvf/bmc/ltlsynth) | stub | `NotImplementedError` |
| Rust prover | stub | parser only; `solve` returns Unknown |

## Benchmark split — policy

The loop must not optimize against the instances it will be evaluated on.

```
benchmarks/
  holdout/    Competition sets (QBFEVAL, SMT-LIB, future SYNTCOMP).
              NEVER used inside the improvement loop. Touched only for
              milestone evaluation runs that are reported, not iterated on.
  train/      Scalable generated families. Each family is a generator
              parameterized by at least one integer (bit-width N, BMC
              bound k, state count n, …) so difficulty is a dial.
  tiny/       Hand-sized correctness regressions (already in tests/integration).
```

A "training" family must:
1. be **generated** (no fixed instance files committed; generator + manifest only),
2. expose a **scale parameter** so the loop can ask "what is the largest N
   solved within budget T?",
3. have a **known expected result** (or be self-dual so SAT/UNSAT is
   determined by construction),
4. compile to DQDIMACS via EQFOB so the same pipeline produces every
   instance.

Initial families (all EQFOB-authored):
- `bitwidth_scaling` — `∃f. ∀x[,y]. f(args) == op(args)` for each BV op,
  swept over `N`.
- `bmc_mutex` — k-step unrolling of a 2-process mutex with one black-box
  arbiter.
- `synthesis_invertibility` — `∃f. ∀x. op(f(x), x) == c` invertibility
  conditions, swept over `N`.
- `dep_cycle` — the §6 cycle counterexample, swept over width; exercises
  SFEx specifically.

## Prerequisites — what must land before the loop can run

Ordered; each gates the next.

### P1. Scalable SAT-certificate verification

Replace enumeration in `tools/verify/sat.py` with the standard
substitute-then-SAT-check:

1. Represent the Skolem certificate as an AIGER circuit (already have a
   writer in `core/aiger.py`; add a reader or keep an in-memory AIG).
2. Substitute each existential's AIG into the matrix → a propositional
   circuit over universals only.
3. Tseitin-encode and hand `¬matrix` to a SAT solver (PySAT / CaDiCaL).
   UNSAT ⇒ certificate valid.

This removes the 2^\|U\| ceiling. UNSAT-side proof replay already
scales.

### P2. Certificate extraction from the prover (not brute force)

`find_skolem` is double-exponential. Replace with extraction from the
saturated clause set / proof structure:

- On SAT (saturation reached), the clause database implicitly defines
  each existential as a function of its dependency set. Extract per-
  existential definitions by Shannon-style cofactoring against the
  dependency set, or by recording which literals were "decided" during
  saturation.
- Short-term acceptable fallback: a per-existential SAT-based
  interpolation against the saturated clause set.

Without P2 the loop can verify UNSAT results at scale but not SAT
results.

### P3. Train-family generators end-to-end

Wire `benchmarks/train/<family>/generate.py` to actually call
`eqfob.parse → typecheck → bitblast → dqdimacs.dump`, write
`.dqdimacs.gz` under a build dir, and emit a `manifest.json` the runner
consumes. One family fully working (`bitwidth_scaling`) is the bar.

### P4. Runner diff

Add `benchmarks/runner/compare.py`:
`compare(baseline.jsonl, candidate.jsonl) → {family: {Δsolved, Δmax_scale, Δmedian_time, regressions: [...]}}`.
"Regression" = any instance that went ok→wrong or ok→timeout.

### P5. SFEx in search

`search.py` must apply `strong_fork_extend` when plain FEx makes no
progress (dependency cycle). Without this the `dep_cycle` family is
unsolvable at any width and the loop has nothing to push on for that
family.

## The loop itself

`scripts/improve_loop.py` (driver) + `benchmarks/runner/compare.py`:

1. **Generate** train instances at the current frontier: for each
   family, generate `N ∈ {N₀, …, N_max_solved + Δ}`.
2. **Baseline** — run current prover, budget `T` per instance, record
   `baseline.jsonl`. Every result goes through `tools/verify`; any
   `wrong` aborts the loop.
3. **Propose** — a change to `provers/forkres/` (heuristic, ordering,
   data structure). The change is a single commit on a scratch branch.
4. **Candidate run** — same instances, same budget → `candidate.jsonl`,
   same verification gate.
5. **Compare** — `compare(baseline, candidate)`. Accept iff:
   - zero `wrong` (already enforced by verify),
   - zero ok→{wrong,error} regressions,
   - net `Δsolved ≥ 0` and `Δmax_scale ≥ 0` summed across families.
6. **Commit or revert.** On accept, fast-forward the working branch and
   the new `candidate.jsonl` becomes the next baseline. On reject, note
   the attempt in `docs/loop_log.md` and revert.
7. Periodically (not every iteration) run against `benchmarks/holdout/`
   and record — **never** feed holdout results back into step 3.

## Next concrete steps

- [x] `benchmarks/{holdout,train}/` split; policy in top-level
      `CLAUDE.md`.
- [x] P0: verifiers decoupled from `provers/`. `tools/verify/unsat.py`
      is self-contained; `tools/verify/sat.py` emits DIMACS CNF + var
      map from a DQDIMACS+AIGER pair (any SAT solver checks it).
- [ ] P1: wire a SAT solver (PySAT or shell-out to CaDiCaL) so the
      runner can call `dqbf-verify sat` and get VALID/INVALID directly.
- [ ] P3: `benchmarks/train/bitwidth_scaling/generate.py` writes real
      `.dqdimacs.gz` + manifest; `dqbf-bench run --family
      train/bitwidth_scaling -D N=2,4,8` works end to end.
- [ ] P4: `benchmarks/runner/compare.py` + `dqbf-bench compare`.
- [ ] P5: SFEx fallback in `search.py`; `dep_cycle` at N=1 returns
      UNSAT with a verified proof.
- [ ] P2: certificate extraction from saturation.
- [ ] `scripts/improve_loop.py` wiring 1–6.
- [ ] EQFOB: implement signed comparisons (needed by several families).
