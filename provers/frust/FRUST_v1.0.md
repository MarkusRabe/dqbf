# frust v1.0

**Commit**: `59a171acf38aedb5b283cf59f27037783ed6b768` (2026-05-03 22:28 UTC)
**Probe**: 1047/1522 on the full train set; 0 invalid certificates.
**LoC**: 1889 across 8 modules.

`provers/frust/` is a single binary built from eight modules. It runs
two phases — **expand** then **saturate** — with the second often
skipped because the first decided already.

## Module map

| File | Lines | What it does |
|---|---:|---|
| `formula.rs` | 158 | Shared `Formula` IR: `n_vars`, `universals`, `deps: Var→Set<Var>`, `clauses`; precomputed `dep_mask: Vec<u64>` for fast ∀-reduce |
| `parse.rs` | 109 | DQDIMACS reader (handles `.gz`) |
| `cdcl.rs` | 499 | Minisat-style CDCL: flat-arena clause storage, two-watched-literals, 1-UIP analyze, VSIDS+phase-saving, assumption-based incremental solving |
| `expand.rs` | 286 | Phase 1 — universal expansion + slot search |
| `search.rs` | 373 | Phase 2 — given-clause Q-resolution saturation with subsumption + FEx |
| `rules.rs` | 180 | `resolve`, bitmask `universal_reduce`, `choose_fork` (FEx) |
| `aiger.rs` | 154 | Skolem truth-tables → `.aag` via BDD-memoized Shannon synthesis |
| `proof.rs` | 88 | `.frp` JSON trace + `Step` builders |
| `main.rs` | 42 | CLI |

## Phase 1: expand (`expand.rs`)

Runs only when `|U| ≤ 16` and `--cert` is requested.

1. **Free pass.** Build one persistent `Cdcl` over the matrix. For each
   of the 2^|U| universal assignments `ub`, call
   `cdcl.solve(assumptions=[universals=ub])` (phase reset each row so
   models stay deterministic). If any row is genuinely UNSAT (not
   budget-exhausted) the DQBF is UNSAT — set `unsat_row` and return.
   Otherwise, for every existential `i` and every dep-key
   `k = ub & dep_mask[i]`, record the model value; the **slot set** is
   `{(i,k) : two rows disagreed}`.

2. **No slots ⇒ SAT.** The free-pass `first_seen` table is already a
   consistent Skolem; emit it.

3. **Slot-DPLL.** Tree-search over slot values: decide one slot at a
   time (preferring its first-seen value), pin only the decided slots
   as assumptions, re-solve every row. CDCL-UNSAT under those pins
   prunes the subtree; a greedy-fill inconsistency on a *non*-slot var
   is a soft conflict — keep deciding. If a leaf is consistent, the
   resulting tables are a Skolem. If the whole tree exhausts, add the
   new soft-conflict pairs to the slot set and retry (≤5 CEGAR rounds).

CDCL learned clauses persist across all rows and all slot-DPLL
iterations, so each row gets cheaper.

## Phase 2: saturate (`search.rs`)

Fork-resolution as a given-clause loop:

- `Db` holds clauses, occurrence lists (lit → clause indices), u64
  signature per clause, dead/processed bitmaps, a length-ordered
  priority queue, and parallel `Proof`/`idx` for `.frp` recording.
- Pop the shortest unprocessed clause; for each literal, resolve
  against partners from `occ[-l]` (only processed, non-dead); ∀-reduce
  the resolvent (bitmask, single pass); skip if seen or
  forward-subsumed (signature fast-reject + sorted-subset check on the
  smallest occ list); otherwise activate it and backward-subsume short
  ones.
- Occ lists are compacted (drop dead entries) every 2048 pops.
- When the queue drains, scan for an information-fork clause, apply
  FEx (`choose_fork`), feed the two halves back in.
- ⊥ derived ⇒ UNSAT with `.frp`. No forks left ⇒ SAT (no cert from
  this path).

If Phase 1 set `unsat_row`, saturation gets only a 1-second window to
find a `.frp`; if it doesn't, return UNSAT-without-proof. If Phase 1
said SAT, Phase 2 never runs.

## Techniques inventory

CDCL (2-watched-lit, 1-UIP, VSIDS hybrid, phase saving, incremental
assumptions) · ∀-expansion · per-key conflict detection for the DQBF
consistency constraint · slot-level DPLL with CEGAR refinement ·
Q-resolution + ∀-reduction · FEx · forward/backward subsumption
(signature-filtered, occ-indexed) · shortest-first given-clause ·
BDD-style Shannon for compact AIGER certs.

## What's *not* there

The simplification pass (iters 31-40 in `CLAUDE.md`) deleted:
HQSpre-style unit/pure/gate-detection preprocessing, the four
heuristic pinned passes that preceded slot-DPLL, the row-model cache,
`find_skolem_brute`, `analyzeFinal`/unsat-core, and SFEx — none earned
their lines on the probe set.
