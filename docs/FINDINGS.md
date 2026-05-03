# Findings

Solver disagreements and encoding issues caught by the
certificate-verification + cross-tool comparison loop. Each entry
should be reproducible from committed sources.

## 2026-05-02 — dqbdd & hqs incorrect UNSAT on `random_bv/under_s0007`

| | |
|---|---|
| Instance | `benchmarks/train/random_bv/v1/under/under_s0007.dqdimacs.gz` |
| Source   | `under_s0007.eqfob` (seed 7, mode=under, width 2) |
| dqbdd / hqs | **UNSAT** |
| pedant | **SAT**, emits Skolem AIG |
| `dqbf-verify sat` | cert **VALID** (kissat: verification CNF UNSAT) |
| Direct AIG eval | all 16 universal assignments satisfy all 1431 clauses |

The formula is SAT; dqbdd and hqs are wrong. Both share the HQSpre
preprocessor, which is the likely culprit. Reproduce:

```sh
zcat benchmarks/train/random_bv/v1/under/under_s0007.dqdimacs.gz > /tmp/u7.dq
third_party/dqbdd/Release/src/dqbdd /tmp/u7.dq        # → UNSAT (wrong)
third_party/hqs/HQS/build/src/hqs/hqs2 /tmp/u7.dq     # → UNSAT (wrong)
third_party/pedant/build/src/pedant /tmp/u7.dq --aag /tmp/u7.aag  # → SAT
dqbf-verify sat /tmp/u7.dq /tmp/u7.aag.adapted --solve            # → VALID
```

**Next step:** delta-minimize the `.dqdimacs` (and ideally the
`.eqfob`) and report upstream.

## Shelved

- `peano_v2_both` flips from SAT (N≤8) to UNSAT (N=16) per hqs+dqbdd.
  Should be SAT at every width by construction. Shelved until a solver
  emits a checkable UNSAT certificate (or forkres reaches it with a
  verified `.frp`).
