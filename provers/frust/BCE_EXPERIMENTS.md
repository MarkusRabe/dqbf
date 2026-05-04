# BCE preprocessing for DQBF — experiment log

Baseline: frust v1.0 (commit `7d2d9d9`), 1046/1522, 0 invalid certs.
Probe: `tests/integration/tiny` + `benchmarks/train`, 10 s, j=24,
SAT certs verified via `tools/verify --solve`.

## Soundness condition

C is **DQBF-blocked** on existential pivot l ∈ C iff for every D with
¬l ∈ D there exists a witness p ∈ C\{l} with ¬p ∈ D and
**dep(var(p)) ⊆ dep(var(l))** (universal p: var(p) ∈ dep(l)). Matches
HQSpre's `checkResolventTautology`.

**Reconstruction.** Walk the removal stack in reverse; for each (C, l)
and each universal assignment α with sk(α) ⊭ C, set
sk[var(l)](α|_dep(l)) := sign(l). Sound because the witness p has
dep(p) ⊆ dep(l), so p(α') = p(α) = false for any α' sharing the
dep(l)-key — every partner clause D ∋ ¬l stays satisfied via ¬p after
the flip.

## Iterations

| iter | change | solved | INVALID | gained / lost |
|---:|---|---:|---:|---|
| 0 | (baseline) | 1046 | 0 | — |
| 1-5 | propositional BCE scaffold + 4 unit tests | — | — | (no probe) |
| 6 | DQBF-BCE wired into expand; reconstruct via 2^\|U\| enumeration | — | 0 | tiny-5 VALID |
| 7 | first probe | 1043 | 0 | +3 / −6 |
| 8 | queue dedup; nc>20k skip; max_stack=10M/2^\|U\|; flat-array reconstruct | 1049 | 0 | +3 / −0 |
| 9 | flat-Vec sk in reconstruct; max_stack 50M tried (slower; reverted to 10M) | — | 0 | tiny-5 VALID |
| 10 | ATE (counter-based UP, reconstruction-free) | 1048 | 0 | +2 / −0 |
| 11 | ATE off; **feed BCE-reduced clauses into saturation** | **1061** | 0 | +15 / −0 |
| 12 | nc-cap removed (step_budget≤200k only) — large BMC still ≥10s; reverted | — | — | — |
| 13 | HTE pass over BCE survivors (ALA via surviving binaries; reconstruction-free) | 1061 | 0 | +15 / −0 |

**Best: iter 13** (= iter 11 + HTE), commits `e285102 → d3f8aed → 78ea982` + this.

### Iter 7 → 8 analysis

The −6 at iter 7 were all 12 s timeouts (baseline ≤ 3.2 s):

- 4× \|U\|=0, 25-48k clauses (`fifo1_*`, `bobcount`, `eijks349`): BCE
  work-queue re-enqueue without dedup is quadratic on high-occ literals.
- `peano_both_n8` (\|U\|=16, BCE removed 965): reconstruct = 2^16 × 965
  × \|C\| ≈ 190M `lit_val` calls (HashMap-backed) ≈ 13 s.
- `collatz_n08_k06` (\|U\|=14): same reconstruct blowup.

Iter 8 fix: `in_queue` HashSet dedup; `nc > 20_000` early-out;
`max_stack = 10M / 2^nu` so reconstruction is bounded; reconstruct
uses flat `Vec<u32>` dep_mask + early-skip when l already correct.

Iter 8 gains (all UNSAT, baseline 12 s timeout):

| instance | base → bce |
|---|---|
| `bmc_circuits_v2/ringbuf_n8_k032` | 12.0 → 9.7 s |
| `bmc_circuits_v2/rr_arbiter_n4_k032` | 12.0 → 1.3 s |
| `cbmc/max3_ge_u005` | 12.0 → 0.6 s |

### Clause-reduction sample (iter 6, before budgeting)

| instance | \|U\| | removed / total |
|---|---:|---|
| `pec_mux2_n4_k2` | 12 | 134 / 168 (80%) |
| `pec_alu_add_n2_k008` | 8 | 38 / 111 (34%) |
| `bmc_mutex_n32_k128` | 15 | 187 / 386 (48%) |
| `peano_both_n8` | 16 | 965 / 2182 (44%) |
| `collatz_n08_k06` | 14 | 3301 / 6994 (47%) |
| `fifo1_n16_k064` | 0 | 6399 / 35135 (18%) |

### Iter 10: ATE

`ate_pass` (counter-based UP per clause). Finds 0-2 removals — BCE
already eliminated most redundancy. Net −1 (overhead pushed
`ringbuf_n8_k032` past 10 s). Disabled; implementation kept with test.

### Iter 11: BCE → saturation

`search.rs` seeds the saturation database from
`dqbf_bce(&g, 0).clauses` (guarded \|U\|<64). `.frp` axioms are by
content so the verifier accepts the subset. **+12 over iter 8.**

- 7× SAT at 0.00 s (`add_n12/16`, `add_zero_n20/24/32`): BCE removes
  *all* clauses; empty matrix is trivially SAT. Provably correct via
  equisat; uncertified (\|U\|>16, reconstruct can't enumerate).
- 4× UNSAT with valid `.frp` (`rr_arbiter`, `conj_k3×2`, `pec_fifo1`).
- 2× UNSAT no-proof (`ringbuf`, `max3` — pre-existing expand-UNSAT path).
- 2× SAT via saturation closure (`pec_mutex_n8_k2_bb{2,3}_complete`).
  By-construction SAT (`_complete` = blackbox is the correct gate).

### Iter 13: HTE

`hte_pass`: ALA(C) via surviving binaries (a∈ALA, (a∨b)∈F\{C} ⇒ add
¬b); if tautological remove C. Reconstruction-free: M⊨F\{C} ∧ M⊭C
gives M[p]=false for all p∈ALA(C) by induction on the binary chain;
ALA(C)⊇{q,¬q} is then a contradiction. Finds 0-17 removals; net 0.

### Not implemented

- **HBCE**: derived sound only for full-dep pivots; the partial-dep
  case fails because ALA-added witnesses propagate via binaries whose
  other endpoint may have dep⊄dep(l). Reverted to HTE-only.
- **CLA**: same reconstruction concern; not attempted.
