# provers/frust/ — standalone Rust DQBF solver

Single-threaded fork-resolution solver. **No code shared** with the
rest of the repo: own DQDIMACS parser, own rule implementations, own
`.frp`/`.aag` writers. The Python verifier in `tools/verify/` is the
correctness oracle — every certificate is checked.

## Build & run

```sh
cargo build --release --manifest-path provers/frust/Cargo.toml
provers/frust/target/release/frust FILE.dqdimacs[.gz] --timeout 10 \
  --cert out.aag --proof out.frp
```

Exit codes 10/20/0 (sat/unsat/unknown).

## Optimization log

Probe set: iters 0-17 use 344 instances (`tests/integration/tiny`,
`bitwidth_scaling`, `random_qbf/v1`, `random_bv/v1`, `peano`); iters
18-20 use the full 804-instance train set. 10 s each. **Zero invalid
certificates at every iteration.**

| iter | bottleneck instance | observation | change | result |
|---:|---|---|---|---|
| 0 | — | naive O(n²) saturation, BTreeSet clauses | baseline | 154/344 |
| 1 | `2qbf_s0001` (9v, 10s) | 51% in `resolve`; whole-db clone per item | Vec\<i32\> clauses + occurrence lists | 194/344; instance still 10s (clause-space explosion) |
| 2 | same | 13270 clauses ≈ 2/3 of 3⁹ clause space | forward+backward subsumption via occ lists | 225/344; instance **7ms** (445 clauses) |
| 3 | `inc_n4` (36v, 95cl, 10s) | 48% in `activate` (subsumption) | u64 signature fast-reject + shortest-first priority queue | 261/344; instance still 10s (Tseitin saturation explodes) |
| 4 | same | only 4 universals → saturation is wrong tool | greedy ∀-expansion + per-row DPLL (SAT-only, cert-producing); fall back on failure | 279/344; instance **7ms** VALID; missing-certs 70→6 |
| 5 | `and_n8` (\|U\|=16, 12s) | 115 MB cert (Shannon = 3·2¹⁶ gates/output) | bitmap BDD-memoized Shannon (fixed cofactor-bit bug); probe substring fix | 289/344; cert **925 B**, 0.93s |
| 6 | `peano_add_n8` (292v, 9.6s) | 32% in DPLL (clones `pol` per branch) | trail-based DPLL (fixed backtrack bug); bitmap Skolem repr | 289/344; instance 5.4s |
| 7 | same, 5.4s | 78% try_expand: 19M HashMap ops + linear unit-prop | flat-array tables + occurrence-driven propagation | 290/344; instance **1.8s** |
| 8 | `peano_v2_mul_n2` (84v, partial deps) | greedy pin causes cross-row conflict | retry with opposite first-branch polarity | 291/344; still UNKNOWN |
| 9 | same | vote-mode no help; `universal_reduce` 5% in BTreeSet | bitmask `universal_reduce` (u64 dep_mask) | 291/344; saturation ~15% faster |
| 10 | `activate` 46% | length-gating fwd subsumption hurt | backward-subsume gate at len≤5 only | 291/344. **Full: frust 490/819 vs forkres 132 vs hqs 705**; 476 verified certs |
| 11 | `add_n12` (\|U\|=24) | Tseitin auxes have no unit/pure | HQSpre unit/pure prep (existentials only) | 291/344; finds 0 on bottlenecks |
| 12 | `peano_v2_mul_n2` | EQFOB emits XOR (4-clause), not AND | static AND-gate detection | 291/344; pattern doesn't match |
| 13 | same | "ever_decided" heuristic **UNSOUND** (`fork_unsat` → SAT) | per-key conflict detection + pinned-pass `row_conflict` guard | 291/344, sound again |
| 14 | same | 4 heuristic seeds all fail; ≤16 conflicting slots | iDQ-style: enumerate 2^slots | 294/344; instance **10ms VALID** |
| 15 | `peano_v2_mul_n3` | enumerating all keys (>16 slots) | enumerate only (i,k) that actually disagreed | 296/344; n3/both_n2 solved |
| 16 | `peano_v2_mul_n4` (32 slots) | 2³² enumeration hopeless | DPLL-over-slots: vote-ordered, backtrack on row fail | 305/344; n4-6 solved |
| 17 | `v2_mul_n8` (192 slots) | 53% in DPLL — re-runs all rows per decision | cache row models keyed by row-local slot-signature | 306/344 (marginal — slots overlap most rows) |
| 18 | `dep_cycle_n1` (11v, 12s) | needs SFEx; also `mutex_n2_k016` ignores --timeout (74s on 3s) | SFEx wired into `choose_fork` | 513/804; dep_cycle still UNKNOWN |
| 19 | `mutex_n2_k016` (\|U\|=0) | DPLL has no conflict bound; saturation inner loop no timeout | conflict cap + tick-based inner check | 513/804; mutex_n2 **16ms** |
| 20 | `mutex_n4_k008` | DPLL exponential on propositional UNSAT | row_budget = 200k/rows; **CDCL identified as next step** | ~511/804 |

![iterations](../../docs/dev_reports/frust_iterations.svg)

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
gain) didn't crack it; bitmask `universal_reduce` and length-gated
backward-subsumption made saturation ~15% faster without unlocking new
instances.

**Iter 11–13: literature-guided preprocessing (no net gain).**
HQSpre's unit/pure-literal elimination found nothing on the bottleneck
Tseitin encodings (every aux occurs in both polarities). Static
AND-gate detection missed EQFOB's 4-clause XOR encoding. The
"ever-decided" definability heuristic was **unsound** — a
unit-propagated value can still differ across dep-equivalent rows
because propagation depends on universals outside the dep set. Replaced
with per-key conflict detection plus a `row_conflict` guard.

**Iter 14–17 (→306): slot search — the big win of round 2.** The
iter-13 conflict detection exposed that on `peano_v2_mul_n2` only 4
(existential, dep-key) pairs actually disagree across rows. Enumerating
those 2⁴ assignments cracked it in 10ms. Restricting enumeration to
keys that *actually* disagreed extended this to n3. At n4 (32 slots),
DPLL-over-slots replaced flat enumeration — vote-ordered decisions,
full-row check, backtrack on failure — solving n4-6. Row-model caching
gave +1 more.

**Iter 18–20: SFEx + budget hygiene.** SFEx wired into `choose_fork`
(used when plain FEx wouldn't shrink the fresh dep-set) but the
partition heuristic doesn't yet find the §6 `dep_cycle` proof. Bigger
find: `mutex_n2_k016` (|U|=0, propositionally UNSAT) ran for 74s on a
3s budget — DPLL had no conflict bound. Per-row budget = 200k/rows
fixed the runaway; tuning is fiddly. **CDCL is the unambiguous next
architecture step** — 1-UIP learning would solve `mutex_n4` in
milliseconds and learned clauses persist across all 2^|U| rows.

## Retrospective (after 20 iterations)

**Probe set too narrow until iter 18.** Optimized against 344 instances
for 17 iterations, then widened to 804 and immediately found
`dep_cycle_n1` (11 vars — the paper's own §6 counterexample) and the
74s-on-3s-timeout bug. Both were sitting there the whole time. Starting
on the full train set would have surfaced them at iter 0.

**Read the relevant papers before re-inventing them.** Iters 8-13 were
six iterations of groping toward what CAQE/iDQ already describe — the
slot-DPLL at iter 16 is their abstraction-refinement loop. Cited those
papers at iter 11 but didn't internalize the technique until 14.
Reading them carefully at iter 4 (when expand was introduced) would
have saved roughly half the iterations.

**Per-instance regression diff.** Iters 10, 13, 19, 20 each *lost*
instances; only noticed because the count dropped. A "which instances
flipped solved→unknown" diff in the probe output would have made each
regression immediately explainable instead of guesswork tuning.

**Stricter cert checking from the start.** The `"VALID" in "INVALID"`
substring bug (iter 5) and the "ever_decided" soundness bug (iter 13)
both slipped because the probe used grep-style checks. The tiny
`fork_unsat` instance that exposed iter 13 should have been a unit test
for `expand` from the moment expand was written.

**Should have built CDCL at iter 6, not deferred it.** Trail-DPLL →
occ-prop → conflict-cap tuning is three iterations spent reimplementing
1/3 of a SAT solver. CDCL with the existing `row_conflict` guard
catching any cert inconsistency would have been safe to ship.

**A `--debug-expand` flag.** Rebuilt-with-eprintln a dozen times to see
slot counts, which strategy fired, where it bailed. A structured debug
dump would have cut each "examine" step in half.

The two that would have moved the needle most: full train set from the
start, and reading CAQE before iter 8.

## Next

- **CDCL** in place of DPLL inside expand (1-UIP, watched literals,
  learned-clause reuse across rows). The single biggest expected gain.
- `dep_cycle`: better SFEx partition heuristic (try all 2-partitions
  of fork pairs, not just the dep-greedy one).
- `add_n12+` (|U|>16): Shannon-per-output-bit instead of
  whole-table expansion (each output bit's cone is small).
| 21 | `mutex_n4_k008` (DPLL exponential) | studied minisat/picosat/satch | 2-watched-lit + 1-UIP CDCL with assumption-based incremental solve; learned clauses persist across rows | ? |
| 22 | `peano_v2_*` regressed (CDCL model drift) | greedy fills pinned as assumptions → CDCL-UNSAT; slot-DPLL decided all-then-check (no pruning) | phase-saving + reset before free pass; pin only slot entries; CEGAR add new conflicts | 506/804 |
