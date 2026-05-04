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
