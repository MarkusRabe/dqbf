# frust — standalone Rust DQBF solver

Single-threaded fork-resolution solver. No code shared with the rest of
the repo: own DQDIMACS parser, own rule implementations, own `.frp`/
`.aag` writers. The Python verifier in `tools/verify/` is the
correctness oracle — every certificate is checked.

```sh
cargo build --release --manifest-path provers/frust/Cargo.toml
provers/frust/target/release/frust FILE.dqdimacs[.gz] --timeout 10 \
  --cert out.aag --proof out.frp
```

Exit codes 10/20/0 (sat/unsat/unknown).

## Optimization log

Probe set: 344 instances from `tests/integration/tiny`,
`bitwidth_scaling`, `random_qbf/v1`, `random_bv/v1`, `peano`. 10 s each.
**Zero invalid certificates at every iteration.**

| iter | solved | bottleneck instance | observation | change |
|---:|---:|---|---|---|
| 0 | 154 | — | naive O(n²) saturation, BTreeSet clauses | baseline |
| 1 | 194 | `2qbf_s0001` (9v, 10s) | 51% in `resolve`; whole-db clone per item | Vec\<i32\> clauses + occurrence lists |
| 2 | 225 | same | 13270 clauses ≈ 2/3 of 3⁹ clause space | forward+backward subsumption |
| 3 | 261 | `inc_n4` (36v, 10s) | 48% in `activate` (subsumption) | u64 signature fast-reject + shortest-first queue |
| 4 | 279 | same | only 4 universals → saturation is wrong tool | greedy ∀-expansion + per-row DPLL (SAT-only, cert-producing) |
| 5 | 289 | `and_n8` (\|U\|=16, 12s) | 115 MB cert (Shannon = 3·2¹⁶ gates/output) | bitmap BDD-memoized Shannon → 925 B cert |
| 6 | 289 | `peano_add_n8` (292v, 9.6s) | 32% in DPLL (clones `pol` per branch) | trail-based DPLL; bitmap Skolem repr |
| 7 | 290 | same, 5.4s | 78% try_expand: 19M HashMap ops + linear unit-prop | flat-array tables + occurrence-driven propagation |
| 8 | 291 | `peano_v2_mul_n2` (84v, partial deps) | greedy pin causes cross-row conflict | retry with opposite first-branch polarity |
| 9 | 291 | same | vote-mode expand no help; `universal_reduce` 5% in BTreeSet | bitmask `universal_reduce` (u64 dep_mask) |
| 10 | 291 | `activate` 46% | length-gating fwd subsumption hurt | backward-subsume gate at len≤5 only |

**Full 819-instance train suite:** frust 490 (476 verified certs) vs
forkres 132 vs hqs 705.

### What each step did

**Iter 0 → 1 (154→194): data structures.** The naive solver used
`BTreeSet<i32>` clauses and cloned the entire database per
given-clause. perf showed 51% of time in `resolve` allocation/
iteration. Switching to sorted `Vec<i32>` clauses with merge-based
resolve and literal-occurrence lists cut the constant factor enough to
pick up 40 instances, but the target 9-variable QBF still timed out —
the issue wasn't data structures.

**Iter 2 (→225): subsumption.** That 9-var instance was generating
~13k clauses — two-thirds of the 3⁹ clause space. Forward subsumption
(skip a new clause if some existing clause is a subset) and backward
subsumption (kill existing supersets) capped it at 445 clauses; the
instance dropped from 10s to 7ms.

**Iter 3 (→261): subsumption indexing.** The new bottleneck
(`inc_n4`, a 36-var Tseitin-encoded adder) spent 48% in subsumption
checks against long occurrence lists. A u64 signature bitmask gives a
one-instruction fast-reject before the full subset test, and a
length-ordered priority queue makes short clauses propagate first. +36
solved, but `inc_n4` itself still exploded — saturation is the wrong
algorithm for that shape.

**Iter 4 (→279): expansion + DPLL.** `inc_n4` has only 4 universals,
so 2⁴ propositional sub-instances cover it. Greedy ∀-expansion solves
each row with a tiny DPLL, threads dependency-consistency by pinning
partial-dep existentials from earlier rows, and emits the resulting
truth tables as a Skolem cert. Sound only for SAT (cert is checkable);
falls back to saturation otherwise. `inc_n4` → 7ms with verified cert;
missing-certs dropped 70→6.

**Iter 5 (→289): cert size.** `and_n8` (16 universals) emitted a
115 MB cert because Shannon expansion is 3·2¹⁶ gates per output.
Packing the truth table into a bitmap and doing BDD-style cofactor
memoization (share identical subfunctions) shrank it to 925 bytes. This
step also surfaced a cofactor-bit-ordering bug that produced an INVALID
cert and a substring bug in the probe (`"VALID" in "INVALID"`) that was
masking it — both fixed before moving on.

**Iter 6–7 (→290): DPLL throughput.** `peano_add_n8` (|U|=16, 292
vars) spent 32% cloning the polarity vector per branch and 11% in
BTreeMap-keyed Skolem tables. A trail-based iterative DPLL (with a
fixed backtrack-polarity-tracking bug), flat-array per-existential
tables instead of HashMaps, and occurrence-driven unit propagation took
it from 9.6s → 1.8s.

**Iter 8–10 (→291): diminishing returns.** The remaining unknowns are
dominated by `peano_v2_*` — instances with mixed `{1,2}` / `{3,4}` /
`∅` dependencies where greedy expansion's row-order pinning genuinely
conflicts. Polarity retry (+1) and a vote-then-pin two-pass mode (no
gain) didn't crack it; these need real inter-row backtracking (a CEGAR
loop). The bitmask `universal_reduce` and length-gated
backward-subsumption made saturation ~15% faster without unlocking new
instances. The hard residue is structural, not constant-factor —
exactly the family where dqbdd/hqs also disagree with pedant.

![iterations](../../docs/dev_reports/frust_iterations.svg)
