# frust development history

`frust` was built from scratch (`1a4f53d`) as a single-threaded Rust
DQBF solver sharing no code with the rest of the repo, then optimized
in short profile-hypothesize-implement-probe cycles. The probe set,
the budget caps, and the architecture all changed along the way; the
constant was that **every emitted certificate is independently
verified** by `tools/verify/` and the loop reverts on any INVALID.

Probe-set sizes shifted across rounds (344 → 804 → 1522 instances) so
absolute counts aren't comparable across section breaks; deltas within
a section are. The full per-iteration table is in the appendix.

---

## Round 1 — saturation, then expansion (iters 0-10, `1a4f53d`..`be0c926`)

**Iter 0 → 1 (154→194/344, `c1cd0e8`): data structures.** The naive
solver used `BTreeSet<i32>` clauses and cloned the entire database per
given-clause. perf showed 51% of time in `resolve` allocation/iteration.
Switching to sorted `Vec<i32>` clauses with merge-based resolve and
literal-occurrence lists cut the constant factor enough to pick up 40
instances, but the target 9-variable QBF still timed out — the issue
wasn't data structures.

**Iter 2 (→225, `fa849f0`): subsumption.** That 9-var instance was
generating ~13k clauses — two-thirds of the 3⁹ clause space. Forward
subsumption (skip a new clause if some existing clause is a subset)
and backward subsumption (kill existing supersets) capped it at 445
clauses; the instance dropped from 10s to 7ms.

**Iter 3 (→261, `42f76fa`): subsumption indexing.** The new bottleneck
(`inc_n4`, a 36-var Tseitin-encoded adder) spent 48% in subsumption
checks against long occurrence lists. A u64 signature bitmask gives a
one-instruction fast-reject before the full subset test, and a
length-ordered priority queue makes short clauses propagate first. +36
solved, but `inc_n4` itself still exploded — saturation is the wrong
algorithm for that shape.

**Iter 4 (→279, `b8e4a67`): expansion + DPLL.** `inc_n4` has only 4
universals, so 2⁴ propositional sub-instances cover it. Greedy
∀-expansion solves each row with a tiny DPLL, threads
dependency-consistency by pinning partial-dep existentials from
earlier rows, and emits the resulting truth tables as a Skolem cert.
Sound only for SAT (cert is checkable); falls back to saturation
otherwise. `inc_n4` → 7ms with verified cert; missing-certs dropped
70→6.

**Iter 5 (→289, `3e7cfe7`): cert size.** `and_n8` (16 universals)
emitted a 115 MB cert because Shannon expansion is 3·2¹⁶ gates per
output. Packing the truth table into a bitmap and doing BDD-style
cofactor memoization (share identical subfunctions) shrank it to 925
bytes. This step also surfaced a cofactor-bit-ordering bug that
produced an INVALID cert and a substring bug in the probe (`"VALID"
in "INVALID"`) that was masking it — both fixed before moving on.

**Iter 6-7 (→290, `13d2424` `81a6fb9`): DPLL throughput.**
`peano_add_n8` (|U|=16, 292 vars) spent 32% cloning the polarity
vector per branch and 11% in BTreeMap-keyed Skolem tables. A
trail-based iterative DPLL (with a fixed backtrack-polarity-tracking
bug), flat-array per-existential tables instead of HashMaps, and
occurrence-driven unit propagation took it from 9.6s → 1.8s.

**Iter 8-10 (→291, `792b9ea` `570155b` `be0c926`): diminishing
returns.** The remaining unknowns are dominated by `peano_v2_*` —
instances with mixed `{1,2}` / `{3,4}` / `∅` dependencies where greedy
expansion's row-order pinning genuinely conflicts. Polarity retry (+1)
and a vote-then-pin two-pass mode (no gain) didn't crack it; bitmask
`universal_reduce` and length-gated backward-subsumption made
saturation ~15% faster without unlocking new instances. First full
9-solver comparison: frust 490/819 vs forkres 132 vs hqs 705, with 476
verified certs — already more than any other solver.

## Round 2 — slot search (iters 11-20, `a079448`..`4265f40`)

**Iter 11-13 (`a079448` `cf226be`): literature-guided preprocessing
(no net gain).** HQSpre's unit/pure-literal elimination found nothing
on the bottleneck Tseitin encodings (every aux occurs in both
polarities). Static AND-gate detection missed EQFOB's 4-clause XOR
encoding. The "ever-decided" definability heuristic was **unsound** —
a unit-propagated value can still differ across dep-equivalent rows
because propagation depends on universals outside the dep set.
Replaced with per-key conflict detection plus a `row_conflict` guard
that rejects any inconsistent table.

**Iter 14-17 (291→306, `e6bc20c` `37e21aa` `fa15d7a` `3b34342`): slot
search — the big win of round 2.** The iter-13 conflict detection
exposed that on `peano_v2_mul_n2` only 4 (existential, dep-key) pairs
actually disagree across rows. Enumerating those 2⁴ assignments
cracked it in 10ms with a verified cert. Restricting enumeration to
keys that *actually* disagreed (not all keys of conflicting vars)
extended this to n3. At n4 (32 slots), DPLL-over-slots replaced flat
enumeration — vote-ordered decisions, full-row check, backtrack on
failure — solving n4-6. Row-model caching gave +1 more.

**Iter 18-20 (`262e42b` `15b7eeb` `7caa574` `4265f40`): SFEx + budget
hygiene.** Widening the probe set to 804 instances immediately found
two long-standing bugs. SFEx was wired into `choose_fork` (used when
plain FEx wouldn't shrink the fresh dep-set) but the partition
heuristic doesn't find the §6 `dep_cycle` proof. Bigger find:
`mutex_n2_k016` (|U|=0, propositionally UNSAT) ran for 74s on a 3s
budget — DPLL had no conflict bound and was backtracking through
2^120. Per-row budget = 200k/rows fixed the runaway; tuning it traded
hard-SAT rows against UNSAT-row deadline. **CDCL was identified as the
unambiguous next architecture step** — 1-UIP learning would solve
`mutex_n4` in milliseconds and learned clauses persist across all
2^|U| rows.

## Round 3 — CDCL and the UNSAT verdict (iters 21-30, `600497d`..`4265f40`)

**Iter 21-24 (→517/804, `600497d` `7dfd1ae` `1485673` `403ec2a`): CDCL
replaces DPLL.** Studied minisat/picosat/satch first, then built a
flat-arena, two-watched-literal, 1-UIP CDCL with assumption-based
incremental solving (`cdcl.rs`, ~490 lines, 4 unit tests). One `Cdcl`
per formula; each row is a `solve(assumptions)` call with learned
clauses persisting. Integration churn took three iterations: learned
clauses cause cross-row model drift → many spurious conflicting slots;
phase-saving + per-row reset stabilizes the free pass; pinning greedy
fills as assumptions caused spurious UNSAT (only pin slot entries);
decide-all-before-check killed pruning (incremental decide with
prune-vs-soft distinction). `analyzeFinal` for cores landed; the
slot-backjump using it was buggy and reverted. 506→517.

**Iter 25-26 (→519, `43c3d57`): VSIDS, hybrid pick.** Minisat-style
activity bumping in `analyze` with 0.95 decay. Pure VSIDS recovered
`under_s9010` but added model variation (-3). Hybrid — first-unset
(deterministic) until the first conflict in a `solve()`, then VSIDS —
kept the gains and recovered all losses.

**Iter 27 (`5a5d093`): subsumption hygiene.** `activate` was 69% on
`2qbf_v2`. Capping forward-subsumption candidates at 64 cut the time
3× but lost `mutex_n4_k004`; replaced with periodic occ-list
compaction (drop dead entries every 2k pops).

**Iter 28-29 (519→679, `8fd0745`): expand-detected UNSAT — the big
win of round 3.** When the free pass finds a row that's CDCL-UNSAT
under universals-only assumptions and `budget_hit=false`, the DQBF is
provably UNSAT — return `Verdict::Unsat` without a `.frp`
(cross-checked 30/30 against hqs). +160 instances in one step. To
recover certificates, iter 29 still gives saturation a 1s window
after expand-UNSAT; if it derives ⊥ the proof is emitted, otherwise
UNSAT-no-cert. Missing-certs 380→173. A safeguard returns UNKNOWN if
expand says UNSAT but saturation says SAT.

**Iter 30 (`4265f40`): MAX_U=20 retry.** With CDCL fast, retried for
`3qbf_v3` (|U|=20). Only +1 (one early UNSAT row); the rest hang in
the 1M-row free pass. Reverted to 16. Those instances need a 2-level
CAQE-style approach.

Final on the 819-instance suite: **frust 642/799** (between pedant 644
and hqs 695), still emitting more verified certs than any other
solver, never on the wrong side of the 7 documented dqbdd/hqs-vs-pedant
disagreements.

## Retrospective after round 3 (`06eb4e8`)

**Probe set too narrow until iter 18.** Optimized against 344 instances
for 17 iterations, then widened to 804 and immediately found
`dep_cycle_n1` (11 vars — the paper's own §6 counterexample) and the
74s-on-3s-timeout bug. Both were sitting there the whole time.

**Read the relevant papers before re-inventing them.** Iters 8-13 were
six iterations of groping toward what CAQE/iDQ already describe — the
slot-DPLL at iter 16 is their abstraction-refinement loop. Reading
them carefully at iter 4 (when expand was introduced) would have saved
roughly half the iterations.

**Per-instance regression diff.** Iters 10, 13, 19, 20 each *lost*
instances; only noticed because the count dropped. A "which instances
flipped solved→unknown" diff in the probe output would have made each
regression immediately explainable.

**Stricter cert checking from the start.** The `"VALID" in "INVALID"`
substring bug (iter 5) and the "ever_decided" soundness bug (iter 13)
both slipped because the probe used grep-style checks.

**Should have built CDCL at iter 6, not deferred it.** Trail-DPLL →
occ-prop → conflict-cap tuning is three iterations spent
reimplementing 1/3 of a SAT solver.

The two that would have moved the needle most: full train set from the
start, and reading CAQE before iter 8.

## Simplification round (`09a411f`, 2404→1889 LoC)

A 10-iteration deletion pass: drop `preprocess.rs` (unit/pure/gate
detection found nothing on bottlenecks), the four heuristic pinned
passes that preceded slot-DPLL, the row-model cache,
`find_skolem_brute`, `analyzeFinal`/unsat-core, SFEx, and the
votes/conflict arrays. Collapse expand to free-pass → if no slots
return Skolem else slot-DPLL. `Step::ured/res/fex` builders replace
five copies of the verbose struct literal. Result: −515 LoC, +2 solved
on the new 1517-instance baseline, 0 invalid. Snapshot recorded as
**v1.0** (`59a171a`, 1047/1522, [`FRUST_v1.0.md`](FRUST_v1.0.md)).

The baseline run also caught a **runner cert-path collision**
(`bde864c`): `bmc_circuits/` and `bmc_circuits_succinct/` share stems
(`shift_reg_n2_k008` etc.), so certs overwrote each other and the
verifier checked the wrong formula → 4 spurious frust + 31 spurious
pedant INVALID. Cert path now `certdir/solver/family/stem`.

## Parallel experiment tracks off v1.0 (`2e045d3` `5799b26`)

Two 20-iteration tracks branched from `7d2d9d9`, each in an isolated
worktree. Both merged to main; combined **1082/1522, 0 INVALID**.
Per-iteration logs: [`PHASE_EXPERIMENTS.md`](PHASE_EXPERIMENTS.md) /
[`BCE_EXPERIMENTS.md`](BCE_EXPERIMENTS.md).

**Track A — phase reordering (+21/-0).** The headline is **outer-∃
CEGAR for the ∃∀∃ shape** (`902069b`, +15): for 16<|U|≤20 where every
existential is either a constant (deps=∅) or full-dep, replace the
3.5s free pass with CEGAR over the constants — pin → scan rows to
first UNSAT → deletion-core → block → re-pick (min-change). Unlocked
18/23 `random_qbf/v3/3qbf` (∃²⁰∀²⁰∃⁴⁰), all VALID Skolem certs.
**Partial-universal expand** (`a48f621`, +3): for |U|>MAX_U, enumerate
the top-16-by-occurrence universals only; row-UNSAT with the rest free
is sound. **Bad-row history** (`12b7481`, +1): check the last 32 bad
rows first so refinement rounds drop to O(1) row scans. Pure
expand↔saturate reordering (iters 2, 3, 7) was ±0: only ~4 unsolved
instances have |U|≤16; on the rest, partial-expand exits in ~0.1s so
saturation already gets full budget regardless of phase order.
Slot-count bailout, fast-leaf (pin all slots at once), and
partial-CEGAR-UNSAT were tried and reverted.

**Track B — Blocked Clause Elimination (+15/-0).** Precise definition,
worked unsoundness example, and reconstruction proof are in
[`BCE.md`](BCE.md). The implementation (`e285102` `d3f8aed`) needed
queue dedup, a clause-count budget, and a `max_stack=10M/2^|U|` cap to
avoid
quadratic re-enqueue and O(2^|U|·|stack|) reconstruction. The big
gain (`78ea982`, +12) was feeding the BCE-reduced clause set to
**saturation as well** — `.frp` axioms are by-content so the verifier
accepts the subset. ATE (net −1) and HTE (net 0) were measured and
disabled; HBCE/CLA derived sound only for full-dep pivots and was
skipped.

The two tracks are nearly orthogonal — only ~1 instance overlaps in
their +sets. After merge: frust 1080/1517, 808 verified certs
(`b0802c9`). frust solves 117 instances pedant doesn't and 41 hqs
doesn't.

## Continual-process redesign (`45bcf54`..`d775db4`)

The cactus plot at v1.0+BCE+phase has a visible shelf at ~1s — the
fixed `.frp` window after expand-UNSAT. ~180 instances are
artificially delayed by ~0.9s waiting for a proof that almost never
arrives.

**Option 1 — adaptive `.frp` window (`45bcf54`, 1082).** Replace the
fixed 1s with `clamp(1.5×expand_time, 50ms, 0.5s)`. <0.5s went
59%→86%; the 0.9-1.2s bucket collapsed 120→19. Same solved count;
~12 fewer `.frp` certs (those that needed >0.5s saturation).

**Option 2 — iterative-deepening partial scan (`69f2ced`, 1083).**
Replace the one-shot top-16 partial scan with levels k=8, 12, 16, 20
over the occurrence-ranked universals; CDCL persists across levels so
each deeper level is cheaper. +1 (`collatz_n24_k12`, |U|=24); UNSAT
rows found at low k finish faster.

**Option 3 — clause-level interleave (`2b9360d` `9651b38`, 1077).**
`solve()` becomes a scheduler: build CDCL once, alternate expand and
saturate slices with geometrically-growing budgets, push saturate's
short Q-resolution-derived clauses into expand's CDCL via
`add_external` between slices. Opt3a (`2b9360d`) ran the existing
`try_expand` in the loop, restarting it from scratch each slice; opt3b
(`9651b38`) rebuilt expand as a resumable `ExpandState` state machine
(`expand_state.rs`, ~480L) so the free pass / outer-CEGAR / slot-DPLL
each pause and resume across slices instead of repeating work. Result:
89% solved <0.5s (vs opt2's 86%), but **−6** vs opt2 on the solved
count — the port lost the min-change re-pick in outer-CEGAR and the
`dpll_cap` bound in slot-DPLL. Both are recoverable; opt3b is kept on
main as the architecture going forward.

**Incremental BCE (`d775db4`, +0).** After each saturate slice, when
the live clause set has grown ≥50%+256, re-run BCE on it and mark
newly-blocked clauses dead. Sound (BCE preserves equisat on any CNF;
already-recorded `.frp` steps stay), but on the current bottleneck
families derived clauses don't expose new blocked clauses. Hook kept
in place.

Largest remaining gap: `bmc_circuits_succinct` (145/150 unsolved; the
succinct encoding has |U|=2m frame-index universals with mixed-dep
existentials — neither track touches this) and `pec_circuits` /
`peano` at |U|≥20 with mixed deps.

---

## Appendix: full iteration table

Probe set: iters 0-17 use 344 instances; iters 18-30 use the full
804-instance train set. 10 s each. Zero invalid certificates at every
iteration.

| iter | bottleneck instance | observation | change | result |
|---:|---|---|---|---|
| 0 | — | naive O(n²) saturation, BTreeSet clauses | baseline | 154/344 |
| 1 | `2qbf_s0001` (9v, 10s) | 51% in `resolve`; whole-db clone per item | Vec\<i32\> clauses + occurrence lists | 194/344; instance still 10s |
| 2 | same | 13270 clauses ≈ 2/3 of 3⁹ clause space | forward+backward subsumption via occ lists | 225/344; instance **7ms** (445 clauses) |
| 3 | `inc_n4` (36v, 95cl, 10s) | 48% in `activate` (subsumption) | u64 signature fast-reject + shortest-first queue | 261/344; instance still 10s |
| 4 | same | only 4 universals → saturation is wrong tool | greedy ∀-expansion + per-row DPLL (SAT-only, cert) | 279/344; instance **7ms** VALID; missing-certs 70→6 |
| 5 | `and_n8` (\|U\|=16, 12s) | 115 MB cert (Shannon = 3·2¹⁶ gates/output) | bitmap BDD-memoized Shannon (fixed cofactor-bit + probe substring bugs) | 289/344; cert **925 B**, 0.93s |
| 6 | `peano_add_n8` (292v, 9.6s) | 32% in DPLL (clones `pol` per branch) | trail-based DPLL (fixed backtrack bug); bitmap Skolem repr | 289/344; instance 5.4s |
| 7 | same, 5.4s | 78% try_expand: 19M HashMap ops + linear unit-prop | flat-array tables + occurrence-driven propagation | 290/344; instance **1.8s** |
| 8 | `peano_v2_mul_n2` (84v, partial deps) | greedy pin causes cross-row conflict | retry with opposite first-branch polarity | 291/344; still UNKNOWN |
| 9 | same | vote-mode no help; `universal_reduce` 5% in BTreeSet | bitmask `universal_reduce` (u64 dep_mask) | 291/344; saturation ~15% faster |
| 10 | `activate` 46% | length-gating fwd subsumption hurt | backward-subsume gate at len≤5 only | 291/344. **Full: 490/819 vs forkres 132 vs hqs 705**; 476 verified certs |
| 11 | `add_n12` (\|U\|=24) | Tseitin auxes have no unit/pure | HQSpre unit/pure prep (existentials only) | 291/344; finds 0 on bottlenecks |
| 12 | `peano_v2_mul_n2` | EQFOB emits XOR (4-clause), not AND | static AND-gate detection | 291/344; pattern doesn't match |
| 13 | same | "ever_decided" heuristic **UNSOUND** (`fork_unsat` → SAT) | per-key conflict detection + pinned-pass `row_conflict` guard | 291/344, sound again |
| 14 | same | 4 heuristic seeds all fail; ≤16 conflicting slots | iDQ-style: enumerate 2^slots | 294/344; instance **10ms VALID** |
| 15 | `peano_v2_mul_n3` | enumerating all keys (>16 slots) | enumerate only (i,k) that actually disagreed | 296/344; n3/both_n2 solved |
| 16 | `peano_v2_mul_n4` (32 slots) | 2³² enumeration hopeless | DPLL-over-slots: vote-ordered, backtrack on row fail | 305/344; n4-6 solved |
| 17 | `v2_mul_n8` (192 slots) | 53% in DPLL — re-runs all rows per decision | cache row models keyed by row-local slot-signature | 306/344 |
| 18 | `dep_cycle_n1` (11v, 12s) | needs SFEx; also `mutex_n2_k016` ignores --timeout (74s on 3s) | SFEx wired into `choose_fork` | 513/804; dep_cycle still UNKNOWN |
| 19 | `mutex_n2_k016` (\|U\|=0) | DPLL has no conflict bound; saturation inner loop no timeout | conflict cap + tick-based inner check | 513/804; mutex_n2 **16ms** |
| 20 | `mutex_n4_k008` | DPLL exponential on propositional UNSAT | row_budget = 200k/rows; **CDCL identified as next step** | ~511/804 |
| 21 | `mutex_n4_k008` (DPLL exponential) | studied minisat/picosat/satch | 2-watched-lit + 1-UIP CDCL with assumption-based incremental solve | (integration churn) |
| 22 | `peano_v2_*` regressed (CDCL model drift) | greedy fills pinned as assumptions → CDCL-UNSAT | phase-saving + reset before free pass; pin only slot entries; CEGAR add new conflicts | 506/804 |
| 23 | `peano_v2_mul_n4` (62 slots, lost) | decide-all-then-check killed pruning | incremental: 1 slot/iter; CDCL-UNSAT prunes subtree, soft-conflict decides more | 517/804 (+11) |
| 24 | `under_s9010` (672 slots) | tried analyzeFinal-based slot backjump; buggy (-6) | reverted; analyzeFinal stays as cdcl.rs infrastructure | 517/804 (held) |
| 25 | linear pick_branch over clauses | minisat VSIDS: bump in analyze, decay 0.95 | +2 -3 (model variation again) |
| 26 | iter-25 lost 3 | VSIDS adds variation when row was conflict-free | hybrid: first-unset until first conflict, then VSIDS | 519/804 (+3, all 3 recovered) |
| 27 | `activate` 69% (subsumption) | tried cap-64 (faster but lost mutex_n4_k004); replaced with periodic occ compaction | 519/804 |
| 28 | `2qbf_v2_*` (expand finds UNSAT row, no proof) | tried CDCL proof-tracing (too large for 1 iter) | return UNSAT-no-proof when free-pass row genuinely UNSAT | **679/804** (+160); missing-certs 13→380; cross-checked 30 vs hqs: 0/30 mismatch |
| 29 | missing-certs 380 | many easy UNSATs lost their proof | 1s saturation window after expand-UNSAT; SAT-vs-expand-UNSAT contradiction → UNKNOWN | 679/804; missing-certs 380→173 |
| 30 | `3qbf_v3_*` (\|U\|=20) | tried MAX_U=20: only +1 (1M-row free pass too slow) | reverted to 16 | 679/804 final |

![iterations](../../docs/dev_reports/frust_iterations.svg)
