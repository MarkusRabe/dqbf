# frust development history

`frust` was built from scratch (`1a4f53d`) as a single-threaded Rust
DQBF solver sharing no code with the rest of the repo, then optimized
in short profile-hypothesize-implement-probe cycles. The probe set,
the budget caps, and the architecture all changed along the way; the
constant was that **every emitted certificate is independently
verified** by `tools/verify/` and the loop reverts on any INVALID.

Probe-set sizes shifted across rounds (344 → 804 → 1522 instances) so
absolute counts aren't comparable across section breaks; deltas within
a section are. The per-iteration tables are in the appendix.

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

Two independent tracks branched from v1.0 (`7d2d9d9`, 1046/1522), each
in an isolated worktree, each running its own 13-15 iteration loop.
Both merged to main; combined **1082/1522, 0 INVALID**. Per-iteration
tables are in the appendix.

### Track A — phase reordering / interleaving (+21/-0)

**Iter A1, A4-5 (→774, `a48f621`): partial-universal expand.** Iter 30
had shown that brute-forcing |U|>16 doesn't scale (1M-row free pass
hangs). Instead, for |U|>MAX_U, rank universals by clause-occurrence
count and enumerate only the top 16; the rest stay as free CDCL
variables. A row that's CDCL-UNSAT under {16 pinned + rest free} means
*every* extension is UNSAT → DQBF UNSAT. SAT from a partial scan tells
you nothing, so it falls through. +3 on `random_bv/v3`. Iter A4 tried
MAX_U=20 directly (+1 −1, wash); A5 settled on PARTIAL_U=16 with
batch-decide for the >16 slot-DPLL.

**Iter A8 (775→790, `902069b`): outer-∃ CEGAR for ∃∀∃ — the
headline.** `random_qbf/v3/3qbf` has the shape ∃²⁰∀²⁰∃⁴⁰: every
existential is either dep-∅ (a "constant" — outer-∃) or full-dep
(inner-∃). At |U|=20 the free pass takes ~3.5s and slot-DPLL never
finishes round 1. Replaced it with CEGAR over the dep-∅ existentials:
pin them to a candidate, scan rows to the first UNSAT, deletion-core
the conflicting subset, learn a blocking clause over the constants,
re-pick (preferring minimum change). Unlocked 18/23 instances with
VALID Skolem certs; +15 in one step.

**Iter A9 (→791, `12b7481`): bad-row history.** After a few CEGAR
rounds the same handful of rows tend to be the witnesses. Checking the
last 32 bad rows first turns each refinement from a full row scan into
O(1). +1 net (one borderline 51-round 3qbf gained, one 8-9s instance
slipped under load).

**Iter A2, A3, A7: pure expand↔saturate reordering — the negative
result.** Bailing slot-DPLL early to give saturation more time (A2,
−3, reverted), tightening the budget split 0.4/0.7 → 0.25/0.5 (A3,
±0), and running 1s pre-saturation only when |U|>MAX_U (A7, ±0) all
landed at zero. The reason: only ~4 unsolved instances have |U|≤16; on
the rest, partial-expand exits in ~0.1s so saturation already gets the
full budget regardless of phase order. There was no scheduling
headroom to find.

**Iter A10-A15: tried and reverted.** Partial outer-CEGAR for
|U|>MAX_U as an UNSAT-only path (A10): `pec_circuits` always have an
outer choice that survives the partial rows, so the condition never
fires. Fast-leaf (A11, pin all slots = `first_seen` and check once):
pinning everything at once hits an assumption-propagation conflict
that the incremental per-slot scans avoid. Dedup of the bad-row
history (A15): made it O(n) and lost 2. The track converged at A9;
A10-A15 were confirmation that nothing simple was left.

### Track B — Blocked Clause Elimination (+15/-0)

The DQBF-safe soundness condition (witness dep ⊆ dep(pivot)), the
worked example showing why plain QBF-BCE is unsound here, and the
reconstruction proof are in [`BCE.md`](BCE.md).

**Iter B1-B6 (`e285102`): scaffold.** Propositional BCE with 4 unit
tests, then the DQBF restriction, then cert reconstruction by walking
the removal stack in reverse and flipping `sk[var(l)]` at every
universal assignment where the model violates a removed clause.
Reconstruction enumerates 2^|U| assignments per stack entry. Tiny-5
VALID; no probe yet.

**Iter B7-B8 (→1049, `d3f8aed`): first probe and the regressions it
exposed.** B7's first full probe came back +3/−6. The six losses were
all 12s timeouts on instances baseline solved in ≤3.2s: four
`fifo1_*`/`bobcount`/`eijks349` at |U|=0 with 25-48k clauses (the BCE
work-queue re-enqueued without dedup — quadratic on high-occurrence
literals), and `peano_both_n8`/`collatz_n08_k06` where reconstruction
cost 2^16 × |stack| × |C| ≈ 190M HashMap-backed `lit_val` calls. B8
fixed all of it: `in_queue` HashSet dedup, an `nc>20k` early-out, a
`max_stack=10M/2^|U|` cap so reconstruction is bounded, and a flat
`Vec<u32>` dep-mask replacing the HashMap. The gains showed up on
saturation-side UNSATs: `rr_arbiter_n4_k032` 12.0s → 1.3s,
`cbmc/max3_ge_u005` 12.0s → 0.6s.

**Iter B11 (1049→1061, `78ea982`): feed BCE into saturation — the
headline.** `synthesis_invertibility/add_n*` is the bottleneck shape:
BCE removes 30-80% of clauses but expand can't use the result (|U|>16,
reconstruction can't enumerate). Feeding the BCE-reduced clause set to
*saturation* as well — sound because `.frp` axiom steps are matched by
content, so the verifier accepts a subset of the input clauses — is
the unlock. +12: seven SAT instances (`add_n12/16`, `add_zero_n20-32`)
where BCE empties the matrix entirely (trivially SAT, uncertified
since |U|>16); four UNSAT with valid `.frp` (`rr_arbiter`, `conj_k3`,
`pec_fifo1`); two SAT via saturation closure on `pec_mutex_*_complete`.

**Iter B10, B13: ATE and HTE — measured and disabled.** Asymmetric
Tautology Elimination (B10, counter-based UP per clause,
reconstruction-free): finds 0-2 removals — BCE has already cleared
the redundancy — and the overhead pushes `ringbuf_n8_k032` past 10s.
Net −1; disabled, implementation kept with test. Hidden Tautology
Elimination (B13, ALA via surviving binaries): finds 0-17 removals,
net 0. Kept enabled since it's reconstruction-free and can only help.

**Not implemented.** HBCE and CLA were derived as sound only for
full-dep pivots — the partial-dep case fails because ALA-added
witnesses propagate via binaries whose other endpoint may have
dep⊄dep(l). With ATE/HTE already at zero, the full-dep-only variants
weren't worth the code.

### After merge

The two tracks are nearly orthogonal — only ~1 instance overlaps in
their +sets. Combined: **1080/1517, 808 verified certs** (`b0802c9`);
frust solves 117 instances pedant doesn't and 41 hqs doesn't.

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

## Refined-loop iteration: `bmc_circuits_succinct` (`a38485b`)

First iteration under the refined `IMPROVEMENT_LOOP.md` (sample ~10,
find commonalities, name the constraint level, expect multiple
attempts at step 4).

**Sample.** 145/445 unsolved are `bmc_circuits_succinct/*` — 45-350
vars, the same circuits we solve fine in unrolled form. |U|=2m (m bits
of t + m bits of t'); existentials with deps `{t}`, `{t'}`, `{t,t'}`,
and one `{}`.

**Observability built.** Slot-DPLL had no debug output in the
ExpandState port — added per-round prints (`slots`, `iters`,
`+conflicts`, `cdcl learned`). Immediately showed:
`shift_reg_n4_k008` exhausts at the **5-round CEGAR cap** with slots
still growing 7→19→still adding; `mutex`/`counter` never finish
round 1 (2¹⁷⁺ slots, `cdcl 0l` — rows are propositionally trivial so
CDCL never prunes).

**Constraint named (architectural).** Slots are *conditionally
defined*: l(t+1) is determined given l(t), but both look like
independent slots to the free pass because l(t) itself varies across
rows. Slot-DPLL searches 2^slots when the answer is unique-given-roots.

**Attempt 1 — raise the cap (`359faf3`).** 5→50. `shift_reg_n4_k008`
solved at round 6. **+6, -0** on probe (all `shift_reg_n4/n8` —
the low-starting-slot variants). `mutex`/`counter`/`gray`/`fifo1`/
`alu_add` unchanged (≥17 starting slots; round 1 never completes).

**Attempt 2 — greedy-pin pass.** Re-added one of the deleted heuristic
passes: process rows in order, pin all filled tables (not just slots).
All 6 sample instances → "row UNSAT" (non-transition rows pin garbage,
later transition rows conflict).

**Attempt 3 — core-based per-row repair.** Re-added `analyzeFinal` to
cdcl.rs; on row-UNSAT, drop core-pinned existentials and retry. **All
6 sample instances → SAT but cert INVALID**: clearing `tables[i][k]`
mid-pass invalidates earlier rows that were checked against the old
value. Added a final validation pass — correctly rejects all 6.

**Attempt 4 — worklist fixpoint.** Re-queue every row touching a
cleared (i,k). Oscillates: row A sets l(t)=1, row B's core clears it,
row A re-sets it. No learning at the table level → no convergence;
bails at 4×rows step cap.

**What stuck.** Cap raise + observability + `analyzeFinal` (for
future use). Fixpoint code reverted.

**Gotchas hit.**
- `analyzeFinal`/`last_core` were deleted in the simplification round;
  had to re-add (and the deletion wasn't noted as "may need this back").
- The first INVALID certs in this session — caught by tiny-5 + sample
  cert-verify before the probe, exactly as the loop intends.
- `iters` counter is local to `step_slot_dpll`, resets per slice; the
  debug print is per-slice cumulative, not lifetime.

**Next (structural).** Slot-dependency analysis: after the free pass,
for each slot s, check if it's *determined* given a subset of other
slots (one CDCL call per candidate: pin the subset, solve, check s is
unit-propagated). Roots are the truly-free slots; the rest propagate.
For BMC-succinct, roots = initial-state bits (~n_latches), trajectory
follows. This is Pedant's definition extraction lifted to the slot
level.

## Refined-loop iteration 2: layered slot propagation (2026-05-05)

Same `bmc_circuits_succinct` family. **Hypothesis**: layer slot
existentials by var-id; decide one layer's slots, propagate (run all
rows pinning what's filled), move to next layer.

**Attempt 1 — layered scan.** Layer 0 fills all 37 existentials in one
pass (good); but the in-layer slice-deadline check bailed before
validation. Removed the check.

**Attempt 2 — looped core-drop.** One-shot retry → looped retry until
core has no existential pins. counter_n2: 306 core-drops, validation
fails at row 16 (the first transition row t=0,t'=1). Non-transition
rows 0-15 filled garbage l(t),l'(0); row 16 needs l'(1)=δ(l(0)), pins
conflict.

**Attempt 3 — constraint-density row ordering.** Process
most-constrained rows first (count active clauses per row). Identical
core-drop counts — ordering had no observable effect.

**Result: +0, all reverted.** Constraint upgraded from architectural
to **research-approach**: greedy SAT-based table reconstruction
without table-level *learning* can't converge here. The right
approach is to encode cross-row consistency into one SAT instance
(iDQ/Pedant) — a substantially different SAT problem per slot, not
just a different scan order.

**Gotchas.** `git checkout --` to revert kept `cdcl.rs` analyzeFinal
(committed in iter 1). The constraint-density closure compiled but
produced identical orderings — likely the universals-only-satisfy
heuristic is too coarse (most clauses have no universal lit after
BCE).

## Refined-loop iteration 3: definability mode for |U|>16 (2026-05-05, `2718668`)

**Target**: `pec_circuits` — 145 unsolved, all SAT, all |U|>16, all
heterogeneous deps. **Constraint named: architectural** —
`Mode::Partial` is UNSAT-only, so frust had *no* SAT path here.
dqbdd/hqs solve these in 0.1 s median; pedant in 1.2 s.

**Hypothesis (validated by Python prototype + reading Pedant source)**:
each existential is either *dep-definable* (Padoa: two-copy SAT
sharing dep(y), `y_A∧¬y_B` UNSAT) or has a tiny choice-space. If all
defined, the unique model-function is the only Skolem candidate;
validate it via one co-SAT loop on `Tseitin(¬matrix) + forcing
clauses`. Undefined-y become *arbiters* (one cell per dep-row, or one
constant when |dep|>8) searched by a third CDCL.

**Change** (4 sub-attempts, multi-file):
- `definability.rs`: selector-gated 2-copy Padoa fixpoint.
- `arbiter.rs`: validity-CEGAR with `analyze_final`-derived forcing
  clauses + per-cell/constant arbiter backtrack.
- `cdcl.rs`: `set_decision()` so unallocated arbiter slots aren't
  decided (300× speedup vs naive pre-alloc).
- `expand_state.rs`: `Mode::Definability` runs first when
  `partial=true`; `Step::Sat(Option<Skolem>)` so SAT-no-cert is
  expressible.

**Result on 1517-overlap: +34/-20 = +14 net.** 0 INVALID; 27/27 new
SAT verdicts confirmed by pedant.

| where | gained | lost | note |
|---|---:|---:|---|
| pec_circuits/_complete | +22 SAT, +1 UNSAT | — | all SAT no-cert (max\|dep\|>20) |
| random_qbf/v3/3qbf | +8 SAT | — | **with** valid cert (\|U\|=20) |
| hwmcc_legacy / bmc / cbmc | +3 UNSAT | -20 | budget eaten by Padoa+CEGAR before fall-through |

**Gotchas.**
- `cmodel` was clobbered by per-y flip-checks → spurious arbiter
  allocation (one (y, dep-row) showed 3885 cells for |dep|=24).
  Separate `scratch` model.
- Pre-allocating 20k arbiter vars made `pick_branch` decide all of
  them — `set_decision(v, false)` skips them.
- `cfg.extract_cert = cert_path.is_some()` means expand never runs
  without `--cert` — bit me twice while testing.
- Six fifo1 `_complete` instances are genuinely UNSAT (frp-validated)
  despite the name — generator artefact, not a frust bug.
- Forcing-clause core can include universals ∉ dep(y) only if
  assumptions leaked — restricting flip-check assumptions to
  `dep_lits` keeps the core ⊆ dep(y).

**Left for iter 4.** CEGAR convergence is the bottleneck (1000+ rounds
× |E| flip-checks; |E|>500 doesn't fit in 3.5 s). Recovering the 20
lost UNSAT means gating definability on a quick "looks circuit-like"
check (e.g., bail if |E|>2000 or unit-prop forces <80% of E). Cert at
max|dep|>20 needs an AIGER-circuit emitter from forcing clauses
instead of truth-tables.

---

## Appendix: iteration tables

Quick-reference; see the corresponding prose section for context.
Zero invalid certificates at every iteration.

### Rounds 1-3 (iters 0-30)

Probe set: iters 0-17 use 344 instances; iters 18-30 use the full
804-instance train set. 10 s each.

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

### Track A — phase reordering (off v1.0, see prose above)

Baseline: 770/995 (worktree-local probe; parent's 1522-set includes
families not generated here).

| iter | hypothesis | result | gained | lost |
|---:|---|---|---|---|
| A0 | (baseline) | 770/995 | — | — |
| A1 | partial-universal expand for \|U\|>16 (UNSAT-only) | 773/995 | +3 random_bv/v3 | — |
| A2 | bail slot-DPLL at >96 slots → saturation | 770/995 | — | −3 peano_v2 (revert) |
| A3 | budget split 0.4/0.7 → 0.25/0.5 | 773/995 | — | — (no headroom) |
| A4 | MAX_U=20, free-pass 0.4 | 773/995 | +1 3qbf_v3 | −1 random_bv/v3 |
| A5 | batch-decide at \|U\|>16; PARTIAL_U=16 split | 774/995 | +1 random_bv recover | — |
| A6 | hoist tables alloc; row-scan deadline check | 775/995 | +1 synth_inv/add_zero_n20 | — |
| A7 | factor saturate(); pre-sat 1s only if \|U\|>MAX_U | 775/995 | — | — (saturate-first ±0) |
| A8 | outer-∃ CEGAR for ∃∀∃ shape, skip free pass | **790/995** | +15 3qbf_v3 (16 SAT VALID) | — |
| A9 | bad-row history (check last 32 first) | 791/995 | +2 3qbf_v3 | −1 3qbf (51-round borderline) |
| A10 | partial outer-CEGAR (UNSAT-only) for \|U\|>MAX_U | 791/995 | — | — (condition too strong for pec) |
| A11 | fast-leaf (all slots=first_seen, 1 scan) | — | — | revert (assumption-prop conflict) |
| A12 | clippy fixes; candidate-units plumbing | 791/995 | — | — |
| A13 | route 16<\|U\|≤20 non-∃∀∃ to PARTIAL_U | 790/995 | — | — (peano \|U\|=20 are SAT) |
| A14 | CEGAR cap 0.9→0.95 | 790/995 | — | — |
| A15 | unsat_only cap 0.3; dedup history (revert) | 790/995 | — | −2 (dedup O(n), revert) |

### Track B — BCE (off v1.0, see prose above; soundness in [`BCE.md`](BCE.md))

Baseline: 1046/1522.

| iter | change | solved | INVALID | gained / lost |
|---:|---|---:|---:|---|
| B0 | (baseline) | 1046 | 0 | — |
| B1-5 | propositional BCE scaffold + 4 unit tests | — | — | (no probe) |
| B6 | DQBF-BCE wired into expand; reconstruct via 2^\|U\| enumeration | — | 0 | tiny-5 VALID |
| B7 | first probe | 1043 | 0 | +3 / −6 |
| B8 | queue dedup; nc>20k skip; max_stack=10M/2^\|U\|; flat-array reconstruct | 1049 | 0 | +3 / −0 |
| B9 | flat-Vec sk in reconstruct; max_stack 50M tried (slower; reverted to 10M) | — | 0 | tiny-5 VALID |
| B10 | ATE (counter-based UP, reconstruction-free) | 1048 | 0 | +2 / −0 |
| B11 | ATE off; **feed BCE-reduced clauses into saturation** | **1061** | 0 | +15 / −0 |
| B12 | nc-cap removed (step_budget≤200k only) — large BMC still ≥10s; reverted | — | — | — |
| B13 | HTE pass over BCE survivors (ALA via surviving binaries) | 1061 | 0 | +15 / −0 |
