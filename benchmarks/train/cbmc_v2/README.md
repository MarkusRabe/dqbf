# benchmarks/train/cbmc_v2/ — paired ok/bug C algorithms, two encodings

Twelve single-loop C algorithms (popcount, parity, bit-reverse,
shift-add multiply, restoring division, subtractive GCD, streaming min,
saturating counter, count-leading-zeros, Fibonacci, token bucket,
one-hot roundtrip), each in a **correct** and a **buggy** variant. The
bug is a localised one-line defect (wrong init, swapped branches,
missing guard) so the ok/bug pair share structure.

Every (family, variant) is swept over `n ∈ {4,6,8}` bit-widths and BMC
bound `k ∈ {8,16,32}` and emitted under **two encodings**:

| dir | encoding | quantifier shape | ground truth |
|---|---|---|---|
| `flat/` | `cbmc --dimacs` on rendered C | all-∃ (propositional) | cbmc's own verdict |
| `succinct/` | `tools.cbmc2dqbf.circuits` → `encode_succinct` | ∀t,t′ ∃ latch(t) — genuine DQBF | analytic, cross-checked at small n |

The flat encoding is the v1 approach: realistic CNF structure but no
quantifier alternation. The succinct encoding builds the same algorithm
as a sequential AIGER (latches = state, output = ¬assert) and applies
the universal-step-counter encoding from `bmc_circuits_succinct/` — so
each latch becomes an existential **function** of the step index. The
two are equisatisfiable per (family, variant, n, k) by construction.

The transition systems are exposed as `SeqAig` via
`tools.cbmc2dqbf.transition.seq_aig_for(name, n, bug)`, so the same
corpus can also feed an inductive-invariant encoding.

Convention (both encodings): SAT ⇔ assertion can fail ⇔ buggy variant.
So `_ok` → expected unsat, `_bug` → expected sat.

To regenerate:

```sh
python -m benchmarks.train.cbmc_v2.generate            # both encodings
python -m benchmarks.train.cbmc_v2.generate --mode succinct
```
