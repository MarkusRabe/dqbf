# benchmarks/eqfob/ — EQFOB benchmark families

These are the **primary** evaluation target. Competition QBF/DQBF sets
are the regression baseline; these families are where we measure what
fork resolution is actually good at.

Each family is a directory containing:

- `generate.py` — builds instances via the `eqfob` Python API; takes
  width params on the CLI.
- `manifest.json` — `[{"params": {...}, "expected": "sat|unsat|unknown"}]`
  for the instances the runner should produce and check.
- `README.md` — what the family measures and why.

Generated `.eqfob` / `.dqdimacs` files are **not** committed (the
generator + manifest are reproducible).

## Families

### `bitwidth_scaling/`

Single-function instances over one BV operation, swept over width `N`.
E.g. "∃f. ∀x. f(x) = x + 1", "∃f. ∀x y. f(x,y) = x * y",
"∃f. ∀x. f(x) > x". Purpose: a per-operator difficulty curve — which BV
ops are easy for fork resolution and which blow up, as a function of `N`.
Evaluation: solve time vs `N`, plotted per operator.

### `sat_unsat/`

Hand-crafted formulas near the satisfiability threshold: minimal
unsat cores, the dependency-cycle counterexample from the journal paper,
random DQBF at varying clause/variable ratio. Purpose: stress the
completeness machinery (SFEx) and certificate extraction on tight
instances. Evaluation: SAT/UNSAT correctness + certificate verification.

### `bmc/`

Bounded model checking instances expressed directly in EQFOB (rather than
via `tools/bmc2dqbf/`): small parameterized protocols (mutex, arbiter,
token ring) with one black-box component. Evaluation: max bound `k`
solved within timeout.

### `synthesis/`

Function-synthesis tasks: invertibility conditions, ranking functions,
bit-twiddling identities ("find `f` such that `f(x) = popcount(x)` using
only `+,&,>>`"). Evaluation: solve time + size of extracted AIGER
certificate.

## Plan

- [ ] `bitwidth_scaling/generate.py` covering `+ - * & | ^ << < ==` for
      `N ∈ {2,4,8,16,32}`.
- [ ] `sat_unsat/` seed set incl. the journal §6 cycle example.
- [ ] `bmc/` 2-process mutex template.
- [ ] `synthesis/` 3–4 bit-twiddling targets.
- [ ] Runner integration: each family registers an `evaluate()` hook that
      turns raw results into the family-specific metric.
