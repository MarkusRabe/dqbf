# CLAUDE.md — dqbf

Guidance for working in this repository.

> **Contributors:** read `INTERNAL.md` (not checked in) before pushing
> anything public. It contains contribution rules that apply to this repo
> and that are intentionally kept out of the public tree.

## What this repo is

A research codebase for **Dependency QBF** centred on the *fork resolution*
proof system (Rabe, "A resolution-style proof system for DQBF"). DQBF
formulas assert the existence of Boolean functions with restricted inputs;
the goal is not just SAT/UNSAT but **extracting those functions** as AIGER
circuits.

Read [`OVERVIEW.md`](OVERVIEW.md) for the theory and literature map before
touching the provers.

## Layout

```
provers/      fork-resolution provers — python (reference) and rust (fast)
tools/
  eqfob/      EQFOB: a typed BV language with ∃-quantified functions → DQBF
  verify/     check AIGER Skolem functions against a (DQ)DIMACS formula
  qbvf2dqbf/  quantified bit-vector → DQBF
  bmc2dqbf/   bounded model checking → DQBF
  ltlsynth2dqbf/  LTL bounded synthesis → DQBF
benchmarks/   competition sets + EQFOB families + parallel runner
tests/        e2e integration only (cadet-style SAT/UNSAT oracles)
docs/         reference material, format specs
```

Each directory has its own `CLAUDE.md` with purpose, references, and a
build-out plan. **Read the local one before editing.**

## Conventions

- **Primary language: Python 3.11+.** Modern typing (`list[str]`,
  `int | None`). Rust only under `provers/rust/`.
- **Formats.** DQBF in DQDIMACS; QBF in QDIMACS; certificates as AIGER
  (ASCII `.aag` for tests, binary `.aig` for large outputs); EQFOB as
  `.eqfob`.
- **Determinism.** Provers and translators must be deterministic for a
  given input + seed; the integration suite diffs outputs.
- **Correctness over speed** in `provers/python/` — it is the reference
  oracle for the Rust prover and for `tools/verify/`.
- **Top-level absolute imports**, no `from .foo import bar`.
- **Separate logic from CLI/jit/dispatch wrappers** so core functions are
  unit-testable without process setup.
- **Tests live next to the code.** `foo.py` → `foo_test.py` in the same
  directory. `tests/` is for end-to-end integration only.

## Dev loop

```bash
pip install -e ".[dev]"
ruff check . && mypy .
pytest                    # unit: discovers *_test.py next to each module
pytest tests/integration  # e2e (slow)
```

Run a single benchmark family:

```bash
dqbf-bench run --family eqfob/bitwidth_scaling --prover python -j 8
```

## When adding a feature

1. If it's a new **encoding** (X → DQBF): add under `tools/`, emit
   DQDIMACS, add at least one `.eqfob` or `.dqdimacs` golden test under
   `tests/integration/`.
2. If it's a new **proof rule / solver heuristic**: implement in
   `provers/python/` first, cover with unit tests, then port to Rust.
3. If it's a new **benchmark family**: add a generator under
   `benchmarks/eqfob/<family>/generate.py` and register it with the
   runner; do **not** commit generated instances >1 MB — commit the
   generator and a small sample.
