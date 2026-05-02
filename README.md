# What is this?

This is an **experiment** to learn how well agentic programming can work for
research that involves hard algorithmic questions. The core of this experiment
is an improvement loop that allows softwware agents to iterate on the algorithms
on their own. This includes a set of benchmarks and a verifier to check the
correctnes of all results.

This repository builds heavily on the work of the SAT and QBF community. In
particular I am using the methodology to build logic solvers, such as the
principle to produce certificates with each result. I am grateful for what
I have learned from that community and perhaps this code might turn out to
be useful to them.

# What is DQBF?

DQBF generalizes QBF by allowing each existential variable to depend on an
explicitly listed subset of universals — equivalently, it asserts the
existence of Boolean functions with restricted argument lists. A satisfying
assignment is a tuple of such functions (Skolem functions); this repository
treats those functions as first-class outputs and emits them as AIGER
circuits.

## Benchmark split: train / valid / test

We borrow the train/valid/test discipline from the machine-learning
community to keep ourselves honest. The risk it guards against is the
same: if you iterate a solver against the very instances you'll be
judged on, you end up with heuristics that exploit accidental structure
in those instances rather than the problem class.

- **`benchmarks/train/`** — what the improvement loop iterates on.
  Many small families (often only 10–20 instances each) drawn from as
  many distinct sources as we can: our own generators (random QBF,
  random BV/EQFOB, BMC unrollings), translated formulas, and known
  corner cases like the dependency-cycle example that needs Strong Fork
  Extension. Every result is independently verified, so the loop never
  has to trust the prover.
- **`benchmarks/valid/`** — held back from the loop but checked
  periodically while developing. Same kinds of families as `train/`
  (different seeds / parameters), plus a few hand-picked instances.
  Used to catch over-fitting before we touch `test/`.
- **`benchmarks/test/`** — competition sets and other externally
  curated benchmarks. **As a rule, competition benchmarks live only
  here.** Touched only for milestone evaluation runs that are reported,
  never iterated on.

Two conventions make the benchmarks auditable:

1. Every generated `.dqdimacs`/`.qdimacs` carries a `c` comment header
   stating where it came from (the script that produced it, the seed,
   the source `.eqfob`/`.aag` if any).
2. The high-level source (`.eqfob`, the AIGER circuit, the generator
   parameters) is committed alongside the compiled DQDIMACS, so the
   *meaning* of an instance is recoverable without re-running anything.

## What's here

| Directory | Purpose |
|---|---|
| `provers/` | One directory per prover; `forkres/` is the fork-resolution prover (Python reference + Rust) |
| `tools/eqfob/` | **EQFOB** — a bit-vector modeling language that compiles to DQBF |
| `tools/verify/` | Certificate checker: validates AIGER Skolem functions against a DQBF |
| `tools/{qbvf,bmc,ltlsynth}2dqbf/` | Front-ends that encode other problems as DQBF |
| `benchmarks/` | QBF/DQBF/QBVF competition sets + new EQFOB families + parallel runner |
| `tests/integration/` | End-to-end SAT/UNSAT regression suite |

See [`OVERVIEW.md`](OVERVIEW.md) for the proof-system background and
literature map.

## Quick start

```bash
pip install -e ".[dev]"
pytest
```

## Status

Early scaffold — most components are plans, not implementations. See the
`CLAUDE.md` in each subdirectory for the build-out roadmap.
