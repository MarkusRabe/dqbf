# Phase reordering / interleaving experiments

**Worktree branch**: `worktree-agent-a7fc850cf5256e88d`
**Baseline (this worktree's 995-instance probe)**: 770/995 solved, 0 invalid.
Note: parent's 1522-instance set includes families not generated here.

| iter | hypothesis | result | gained | lost |
|---:|---|---|---|---|
| 0 | (baseline) | 770/995 | — | — |
| 1 | partial-universal expand for \|U\|>16 (UNSAT-only) | 773/995 | +3 random_bv/v3 | — |
| 2 | bail slot-DPLL at >96 slots → saturation | 770/995 | — | −3 peano_v2 (revert) |
| 3 | budget split 0.4/0.7 → 0.25/0.5 | 773/995 | — | — (no headroom) |
| 4 | MAX_U=20, free-pass 0.4 | 773/995 | +1 3qbf_v3 | −1 random_bv/v3 |
| 5 | batch-decide at \|U\|>16; PARTIAL_U=16 split | 774/995 | +1 random_bv recover | — |
| 6 | hoist tables alloc; row-scan deadline check | 775/995 | +1 synth_inv/add_zero_n20 | — |
| 7 | factor saturate(); pre-sat 1s only if \|U\|>MAX_U | 775/995 | — | — (saturate-first ±0) |
| 8 | outer-∃ CEGAR for ∃∀∃ shape, skip free pass | **790/995** | +15 3qbf_v3 (16 SAT VALID) | — |
| 9 | bad-row history (check last 32 first) | 791/995 | +2 3qbf_v3 | −1 3qbf (51-round borderline) |
| 10 | partial outer-CEGAR (UNSAT-only) for \|U\|>MAX_U | 791/995 | — | — (condition too strong for pec) |
| 11 | fast-leaf (all slots=first_seen, 1 scan) | — | — | revert (assumption-prop conflict; incremental's intermediate scans matter) |
| 12 | clippy fixes; candidate-units plumbing | 791/995 | — | — |
| 13 | route 16<\|U\|≤20 non-∃∀∃ to PARTIAL_U | 790/995 | — | — (peano \|U\|=20 are SAT) |
| 14 | CEGAR cap 0.9→0.95 | 790/995 | — | — |
| 15 | unsat_only cap 0.3; dedup history (revert) | 790/995 | — | −2 (dedup O(n), revert) |

**Final**: 791/995 standalone, 790 under -j8 load (2 borderline 3qbf at 8-9s). +21 over baseline, 0 INVALID.

## What worked

1. **Outer-∃ CEGAR for ∃∀∃ shape (iter 8, +15)** — the dominant gain. For
   16<|U|≤20 with every existential either constant or full-dep, CEGAR
   over the constants (deletion-core, min-change preference, skip free
   pass) replaces the unscalable 1M-row slot-DPLL. Unlocked 18/23
   `random_qbf/v3/3qbf` (∃²⁰∀²⁰∃⁴⁰), all VALID Skolem certs.
2. **Partial-universal expand (iter 1, +3)** — for |U|>MAX_U, enumerate
   the top-PARTIAL_U universals; row-UNSAT with the rest free is sound.
   +3 `random_bv/v3`.
3. **bad-row history (iter 9, +1)** — check the last 32 bad rows first;
   refinement rounds become O(1) row scans.

## What didn't

- Pure expand↔saturate reordering (iters 2,3,7): **±0**. Only ~4
  unsolved instances have |U|≤16; on the rest, partial-expand exits in
  ~0.1s so saturation already gets full budget and either times out or
  hits the 200k-clause cap. There is no scheduling headroom.
- Partial outer-CEGAR for UNSAT (iter 10): condition too strong;
  pec_circuits all have an outer choice that survives partial rows.
- fast-leaf (iter 11): pinning all slots at once hits an
  assumption-propagation conflict that incremental's per-slot scans avoid.
