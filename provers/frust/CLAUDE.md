# provers/frust/ — standalone Rust DQBF solver

Single-threaded fork-resolution prover. **No code shared** with the
rest of the repo: own DQDIMACS parser, own rule implementations, own
`.frp`/`.aag` writers. The Python verifier in `tools/verify/` is the
correctness oracle.

## Build & run

```sh
cargo build --release --manifest-path provers/frust/Cargo.toml
target/release/frust FILE.dqdimacs[.gz] --timeout 10 \
  --cert out.aag --proof out.frp
```

Exit codes 10/20/0 (sat/unsat/unknown).

## Iteration log

| iter | bottleneck instance | observation | change | result |
|---|---|---|---|---|
| 0 | — | naive O(n²) saturation, BTreeSet clauses | baseline | 154/344, 0 invalid |
| 1 | `2qbf_s0001` (9 vars, 10s) | 51% in `resolve`; whole-db clone per item | Vec\<i32\> clauses + occurrence lists | 194/344, 0 invalid; instance still 10s (clause-space explosion) |
| 2 | same | 13270 clauses ≈ 2/3 of 3⁹ clause space | forward+backward subsumption via occ lists | 225/344, 0 invalid; instance now **7ms** (445 clauses) |
| 3 | `inc_n4` (36v, 95cl, 10s) | 48% in `activate` (subsumption); long occ lists | u64 signature fast-reject + shortest-first priority queue | 261/344, 0 invalid; instance still 10s (Tseitin saturation explodes) |
| 4 | same | only 4 universals → saturation is wrong tool | greedy ∀-expansion + per-row DPLL (SAT-only, cert-producing); fall back on failure | 279/344, 0 invalid; instance now **7ms** with VALID cert; missing-certs 70→6 |
| 5 | `and_n8` (47v, \|U\|=16, 12s) | 115 MB cert (Shannon = 3·2¹⁶ gates/output) | bitmap-packed BDD-style memoized Shannon (fixed cofactor-bit bug); probe substring fix | 289/344, 0 invalid; cert **925 B**, 0.93s |
| 6 | `peano_add_n8` (292v, 9.6s) | 32% in DPLL (clones `pol` per branch), 11% BTreeMap Skolem | trail-based DPLL (fixed backtrack bug); bitmap Skolem repr | 289/344, 0 invalid; instance 5.4s |
| 7 | same, 5.4s | 78% try_expand: 19M HashMap hashes + linear-scan unit-prop | flat-array tables + occurrence-driven propagation | 290/344, 0 invalid; instance **1.8s** |
| 8 | `peano_v2_mul_n2` (84v, partial deps) | greedy pin causes cross-row conflict | retry expand with opposite first-branch polarity | 291/344, 0 invalid; instance still UNKNOWN (need real inter-row search) |
| 9 | same; `universal_reduce` 5% (BTreeSet ops) | tried vote-mode expand (no help on this instance); pivoted to bitmask `universal_reduce` (u64 dep_mask) | 291/344, 0 invalid; saturation ~15% faster |
| 10 | `activate` 46% (subsumption) | length-gating fwd subsumption hurt (junk slips in); kept backward-only gate at len≤5 | 291/344, 0 invalid. **Full bench: frust 490/819 vs forkres 132/819 vs hqs 705**; 476 verified certs |
| 11 | `add_n12` (\|U\|=24) | Tseitin auxes have no unit/pure | HQSpre unit/pure prep (existentials only) | 291/344; finds 0 on bottlenecks |
| 12 | `peano_v2_mul_n2` | EQFOB emits XOR (4-clause), not AND | static AND-gate detection; skip in pin loop | 291/344; pattern doesn't match |
| 13 | same | "ever_decided" heuristic UNSOUND (`fork_unsat` → SAT) | replaced with per-key conflict detection + pinned-pass `row_conflict` guard | 291/344, sound again |
| 14 | same | 4 heuristic seeds all fail; ≤16 conflicting slots | iDQ-style: enumerate 2^slots when slots≤16 | 294/344, instance **10ms VALID** |
| 15 | `peano_v2_mul_n3` | enumerating ALL keys of conflicting vars (>16 slots) | enumerate only the (i,k) pairs that actually disagreed; cap 20 | 296/344, n3/both_n2 solved |
| 16 | `peano_v2_mul_n4` (32 slots) | 2^32 enumeration hopeless | DPLL-over-slots: vote-ordered, backtrack on row fail | 305/344, n4-6 solved |
| 17 | `v2_mul_n8` (192 slots) | 53% in DPLL — re-runs all rows per slot decision | cache row models keyed by row-local slot-signature | 306/344, marginal (slots overlap most rows) |
| 18 | `dep_cycle_n1` (11v, 12s) — needs SFEx | also `mutex_n2_k016` ignores --timeout (74s on 3s) | SFEx wired into choose_fork | 513/804; dep_cycle still UNKNOWN (partition heuristic) |
| 19 | `mutex_n2_k016` (\|U\|=0, 74s on --timeout 3!) | DPLL has no conflict bound; saturation inner loop no timeout check | DPLL_MAX_CONFLICTS=200k; tick-based inner check | 513/804; mutex_n2 16ms |
| 20 | `mutex_n4_k008` (\|U\|=0, expand DPLL exponential on UNSAT) | DPLL conflict budget unbounded for rows=1 | budget=clamp(1M/rows, 100, 50k); decided CDCL is the right next step | ? |
