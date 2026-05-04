# Phase reordering / interleaving experiments

**Worktree branch**: `worktree-agent-a7fc850cf5256e88d`
**Baseline (this worktree's 995-instance probe)**: 770/995 solved, 0 invalid.
Note: parent's 1522-instance set includes families not generated here.

| iter | hypothesis | result | gained | lost |
|---:|---|---|---|---|
| 0 | (baseline) | 770/995 | — | — |
| 1 | partial-universal expand for \|U\|>16 (UNSAT-only) | 773/995 | +3 random_bv/v3 | — |
| 2 | bail slot-DPLL at >96 slots → saturation | 770/995 | — | −3 peano_v2 (revert) |
