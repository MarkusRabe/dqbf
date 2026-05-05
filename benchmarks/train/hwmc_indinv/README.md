# hwmc_indinv

Hardware model checking via **inductive-invariant search**, the dual of
`../bmc_circuits/`. Instead of asking "∃ trace of length k reaching
bad" we ask "∃ invariant `Inv : 2^|state| → bool` with `init → Inv`,
`Inv ∧ T → Inv'`, `Inv → ¬bad`" — the IC3/PDR three-clause obligation
(Bradley'11; Een–Mishchenko–Brayton FMCAD'11), expressed directly as a
DQBF Skolem function.

> **Semantics flip.** SAT here means an invariant **exists**, i.e. the
> safety property **holds**. UNSAT means no Boolean invariant of state
> exists — since the reachable-set itself is always inductive, UNSAT ⇔
> bad is reachable. This is the opposite polarity from BMC.

The encoding (`tools/hwmc2dqbf_indinv/encode.py`) introduces two
existential bits `inv` with `dep={s}` and `inv'` with `dep={s'}`, then
ties them to the same Skolem function via the consistency clause
`(s = s') → (inv ↔ inv')` — the same isomorphic-dep trick as
`bmc_circuits/succinct`. The result is genuine DQBF (the two dep-sets
are incomparable).

## Variants

| circuit | original | buggy |
|---|---|---|
| mutex, fifo1, alu_add | bad unreachable → **SAT** | fault injected → **UNSAT** |
| counter, gray, shift_reg | bad reachable → **UNSAT** | — |

5 widths × 9 variants = 45 instances. `expected` is set in the manifest
by construction (no solver probe).

## What it stresses

A SAT certificate is the invariant itself — a single-bit Skolem
function over all latches (`|dep| = L`, up to 96 for `alu_add n=32`).
Solvers that build truth-table certs blow up; solvers that extract
circuit-shaped certs (interpolants, gate definitions) should handle
the safe instances cheaply since the invariants are structurally
simple (e.g. `mutex`: "≤1 grant high").
