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

## 2026-05-03 — dqbdd & hqs incorrect UNSAT on `peano_v2_both` (N=2..8)

| | |
|---|---|
| Instances | `benchmarks/train/peano/instances/peano_v2_both_n{2,3,4,5,6,8}.dqdimacs.gz` |
| Source    | `peano_v2_both_n{N}.eqfob` (∃s,add,mul. successor + Peano add/mul axioms) |
| dqbdd / hqs | **UNSAT** on all 6 |
| pedant | **SAT** on all 6, emits Skolem AIG |
| `dqbf-verify sat` | all 6 certs **VALID** (kissat: verification CNF UNSAT) |

The formulas are SAT by construction (s=inc, add=+, mul=× over bv[N]).
Same dqbdd+hqs failure mode as `under_s0007` above, now on a
structurally simple, scalable family. At N≥10 pedant times out so the
cert-based verdict is not yet available there.

**This strengthens the HQSpre hypothesis** — 7 confirmed incorrect-UNSAT
instances, 6 of which are parametric and minimal-ish already.

## Shelved

(nothing currently)
