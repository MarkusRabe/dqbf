# dqbf

Provers and tooling for **Dependency Quantified Boolean Formulas (DQBF)**,
built around the *fork resolution* proof system.

DQBF generalizes QBF by allowing each existential variable to depend on an
explicitly listed subset of universals — equivalently, it asserts the
existence of Boolean functions with restricted argument lists. A satisfying
assignment is a tuple of such functions (Skolem functions); this repository
treats those functions as first-class outputs and emits them as AIGER
circuits.

## What's here

| Directory | Purpose |
|---|---|
| `provers/` | Fork-resolution provers (reference Python, performance Rust) |
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
