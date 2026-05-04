# Exploratory experiments off v1.0 (`59a171a`)

Two parallel 20-iteration tracks branched from `7d2d9d9`, each in an
isolated worktree. Both merged back to main; combined result
**1082/1522, 0 INVALID** (v1.0 baseline 1047).

## Track A — Phase reordering / interleaving

**Result: +21/-0, 0 INVALID.** Converged at iter 9. Full log:
`PHASE_EXPERIMENTS.md`.

### What worked

| Technique | Commit | Gain | Unlocked |
|---|---|---:|---|
| Outer-∃ CEGAR for ∃∀∃ shape | `902069b` | +15 | `random_qbf/v3/3qbf` 18/23 (was 0) |
| Partial-universal expand (top-16-by-occurrence when \|U\|>MAX_U) | `a48f621` | +3 | `random_bv/v3` |
| Bad-row history (check last-32 first) | `12b7481` | +1 | — |

The outer-∃ CEGAR is the headline: for 16<|U|≤20 where every
existential is either a constant (deps=∅) or full-dep, replace the
3.5s free pass with CEGAR over the constants — pin → scan rows to
first UNSAT → deletion-core → block → re-pick (min-change). All
`random_qbf/v3/3qbf` SAT certs verified.

### What didn't

Pure expand↔saturate reordering (iters 2, 3, 7) is **±0**: only ~4
unsolved instances have |U|≤16; on the rest, partial-expand exits in
~0.1s so saturation already gets full budget and hits its 200k-clause
cap regardless. Slot-count bailout, fast-leaf, and partial-CEGAR-UNSAT
were tried and reverted.

### Remaining

`pec_circuits` (145 unsolved, |U|≥24, mixed deps) and `peano` (34,
|U|≥20, mixed deps) — neither reachable by phase reordering; both
need a |U|>20 SAT path with mixed-dep consistency.

## Track B — Blocked Clause Elimination

**Result: +15/-0, 0 INVALID.** Full log: `BCE_EXPERIMENTS.md`.

### Soundness

A clause C is **DQBF-blocked on existential `l`** iff every partner
D∋¬l has a witness `p ∈ C\{l}` with `¬p ∈ D` and `dep(p) ⊆ dep(l)`.
Matches HQSpre's `checkResolventTautology`. Reconstruction walks the
removal stack in reverse: for each `(C,l)` and universal assignment α
with `sk⊭C(α)`, set `sk[var(l)](α|_dep(l)) := sign(l)`. The dep-subset
condition guarantees the witness's value is fixed across the
`dep(l)`-equivalence class, so every partner clause stays satisfied
after the flip.

### What worked

| Technique | Commit | Gain | Unlocked |
|---|---|---:|---|
| DQBF-safe BCE in expand | `e285102` | +3 | `synth_inv/add_n*` (BCE empties matrix) |
| Budget tuning + flat reconstruct | `d3f8aed` | +3 | misc |
| BCE-reduced clauses → saturation | `78ea982` | +12 | `pec_mutex_*`, 4 UNSAT with `.frp` |

### What didn't

- **ATE** (asymmetric tautology elim via counter-based UP): 0-2
  removals on the bottlenecks; net −1. Disabled.
- **HTE** (hidden tautology via ALA over surviving binaries):
  reconstruction-free and sound, but 0-17 removals; net 0. Kept as a
  no-op pass.
- **HBCE/CLA**: derived sound only for full-dep pivots — partial-dep
  fails because ALA-added witnesses propagate via binaries with
  `dep ⊄ dep(l)`. Skipped per the zero-INVALID constraint.

## Combined effect

| Variant | Solved /1522 | Δ | Notable family |
|---|---:|---:|---|
| v1.0 | 1047 | — | — |
| +BCE | 1061 | +14 | `synthesis_invertibility` 44→48 |
| +phase | ~1068 | +21 | `random_qbf/v3` ~30→53 |
| +both | **1082** | **+35** | both above |

The two tracks are largely **orthogonal**: BCE shrinks the clause set
(helps everything a bit, dominates on Tseitin-heavy `synth_inv`);
phase-interleave's outer-CEGAR opens a new |U|-range. Only ~1
instance overlaps in their respective +sets.

## Next

- `bmc_circuits_succinct` (145/150 unsolved): the succinct encoding
  has |U|=2m universals (frame indices t, t') with mixed-dep
  existentials. Neither track touches this. Needs a frame-aware
  expansion (enumerate t,t' pairs) or a BDD-based approach.
- Full HBCE for full-dep-only pivots (the soundness condition the
  agent derived) — small but free.
