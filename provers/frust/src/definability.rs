//! Padoa-style definability detection. An existential `y` is
//! *dep-definable* iff any two models of the matrix that agree on
//! `dep(y)` also agree on `y` — i.e. the matrix uniquely determines
//! `y` as a function of `dep(y)`.
//!
//! Check: build two copies of the matrix (vars 1..n and n+1..2n),
//! link `dep(y)` across copies via selector-guarded equiv clauses,
//! assume `y_A ∧ ¬y_B`. UNSAT ⇒ defined. Iterate to fixpoint,
//! additionally linking already-defined `z` with `dep(z) ⊆ dep(y)`
//! (sound: such `z` are functions of `dep(y)`, so linking them adds
//! no information beyond what linking `dep(y)` already implies).
//!
//! Reference: Slivovsky, "Interpolation-based semantic gate
//! extraction" (SAT'20); Reichl/Slivovsky/Szeider, "Pedant" (SAT'21).

use crate::cdcl::Cdcl;
use crate::formula::{var, Clause, Formula, Lit, Var};
use crate::interpolant::{mcmillan, Itp, Side};
use std::collections::{BTreeSet, HashMap, HashSet};

pub struct DefSplit {
    pub defined: Vec<Var>,
    pub undefined: Vec<Var>,
    /// Of `defined`, how many are unit-propagation constants. They
    /// don't need an interpolation pass (constant `Itp`) so the |E|
    /// gate in `step_definability` should subtract them — the
    /// interpolation cost is `O(|defined ∖ constants| + |undefined|)`,
    /// not `O(|E|)`.
    pub n_const: usize,
}

pub struct Def {
    pub itp: Itp,
    pub root: u32,
}

/// BCP `f.clauses` from the empty assignment. Returns `value[v]` ∈
/// {-1,0,1} per var (1-based; index 0 unused). Existentials with a
/// non-zero value are unit-propagated constants — trivially defined,
/// no Padoa check needed, and their interpolant is the constant.
///
/// This is the "pre-filter unit-propagated existentials" step (iter106):
/// for circuit-like matrices a large fraction of e-vars are propagated
/// constants (Tseitin gates over already-pinned inputs), and skipping
/// the per-`y` 2-copy CDCL clone for them frees the budget for the
/// genuinely hard ones.
pub fn unit_prop_constants(f: &Formula) -> Vec<i8> {
    let n = f.n_vars as usize;
    let mut value = vec![0i8; n + 1];
    let mut occ: Vec<Vec<usize>> = vec![Vec::new(); 2 * (n + 1)];
    let lidx = |l: Lit| -> usize { 2 * var(l) as usize + if l > 0 { 0 } else { 1 } };
    for (ci, c) in f.clauses.iter().enumerate() {
        for &l in c {
            occ[lidx(l)].push(ci);
        }
    }
    let mut q: Vec<Lit> = f
        .clauses
        .iter()
        .filter(|c| c.len() == 1)
        .map(|c| c[0])
        .collect();
    while let Some(l) = q.pop() {
        let v = var(l);
        let want = if l > 0 { 1i8 } else { -1 };
        if value[v as usize] != 0 {
            if value[v as usize] != want {
                // Conflict at level 0 — formula propositionally UNSAT.
                // The Padoa loop will surface that; just stop here.
                return value;
            }
            continue;
        }
        value[v as usize] = want;
        // Watch clauses where ¬l appears: they may have become unit.
        for &ci in &occ[lidx(-l)] {
            let mut un: Option<Lit> = None;
            let mut sat = false;
            for &m in &f.clauses[ci] {
                let mv = var(m) as usize;
                if value[mv] == 0 {
                    if un.is_some() {
                        un = None;
                        break;
                    }
                    un = Some(m);
                } else if (value[mv] > 0) == (m > 0) {
                    sat = true;
                    break;
                }
            }
            if !sat {
                if let Some(u) = un {
                    q.push(u);
                }
                // un=None && !sat: all-false → conflict; surface later.
            }
        }
    }
    value
}

/// Padoa fixpoint with selector-guarded link clauses so a single
/// incremental CDCL instance serves all per-y checks. Returns `None`
/// if the budget runs out before converging.
pub fn padoa_split(
    f: &Formula,
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
) -> Option<DefSplit> {
    let n = f.n_vars as Lit;
    let shift = |l: Lit| -> Lit {
        if l > 0 {
            l + n
        } else {
            l - n
        }
    };

    // Var layout:
    //   1..n         copy A
    //   n+1..2n      copy B
    //   2n+1..       one selector per var (universal or existential)
    let link_vars: Vec<Var> = {
        let mut v: Vec<Var> = f.universals.iter().copied().collect();
        v.extend(f.deps.keys().copied());
        v.sort_unstable();
        v
    };
    let sel: HashMap<Var, Lit> = link_vars
        .iter()
        .enumerate()
        .map(|(i, &v)| (v, 2 * n + 1 + i as Lit))
        .collect();
    let total_vars = 2 * n as usize + link_vars.len();

    let mut clauses: Vec<Clause> = Vec::with_capacity(2 * f.clauses.len() + 2 * link_vars.len());
    for c in &f.clauses {
        clauses.push(c.clone());
        clauses.push(c.iter().map(|&l| shift(l)).collect());
    }
    for &v in &link_vars {
        let s = sel[&v];
        let a = v as Lit;
        let b = shift(a);
        clauses.push(vec![-s, -a, b]);
        clauses.push(vec![-s, a, -b]);
    }
    let mut cdcl = Cdcl::new(total_vars, &clauses);
    let mut model = vec![0i8; total_vars + 1];

    let live: HashSet<Var> = f
        .clauses
        .iter()
        .flat_map(|c| c.iter().map(|&l| var(l)))
        .filter(|v| f.deps.contains_key(v))
        .collect();
    let deps: HashMap<Var, BTreeSet<Var>> = f.deps.iter().map(|(&y, d)| (y, d.clone())).collect();
    // Bitset dep representation (same as `extract_interpolants`): the
    // defined-z subset filter is `O(|todo| × |defined| × |U|)` per
    // pass — quadratic in |E| with the BTreeSet walk. (iter80 perf:
    // ~4.5% wall on `pec_fifo1_n20`.)
    let nu_words = f.universals.len().div_ceil(64);
    let u_idx: HashMap<Var, usize> = f
        .universals
        .iter()
        .enumerate()
        .map(|(i, &u)| (u, i))
        .collect();
    let dep_bits: HashMap<Var, Vec<u64>> = f
        .deps
        .iter()
        .map(|(&y, d)| {
            let mut b = vec![0u64; nu_words];
            for &u in d {
                let i = u_idx[&u];
                b[i / 64] |= 1u64 << (i % 64);
            }
            (y, b)
        })
        .collect();
    let is_sub = |z: &[u64], y: &[u64]| z.iter().zip(y).all(|(&a, &b)| a & !b == 0);

    // Pre-filter: existentials that BCP to a constant from the empty
    // assignment are trivially dep-defined (constant Skolem). Skipping
    // them in the Padoa loop is the iter106 fix — for circuit-like
    // matrices (`pec_alu_add_n8`: 2134 e-vars) a chunk are Tseitin
    // gates over pinned inputs and don't need a 2-copy CDCL solve.
    let prop = unit_prop_constants(f);
    let n_prop_const = f
        .deps
        .keys()
        .filter(|&&y| live.contains(&y) && prop[y as usize] != 0)
        .count();
    if debug && n_prop_const > 0 {
        eprintln!(
            "c [def] unit-prop pre-filter: {} of {} live e-vars are constants",
            n_prop_const,
            live.len()
        );
    }
    let mut defined: Vec<Var> = f
        .deps
        .keys()
        .copied()
        .filter(|&y| !live.contains(&y) || prop[y as usize] != 0)
        .collect();
    let mut is_defined: HashSet<Var> = defined.iter().copied().collect();
    let mut todo: Vec<Var> = live
        .iter()
        .copied()
        .filter(|&y| prop[y as usize] == 0)
        .collect();
    todo.sort_by_key(|&y| (deps[&y].len(), y));

    let budget_per = ((1_000_000 / live.len().max(1)) as u64).max(500);
    let mut rounds = 0usize;
    loop {
        rounds += 1;
        let mut still: Vec<Var> = Vec::new();
        let mut progress = false;
        for &y in &todo {
            if start.elapsed().as_secs_f64() >= deadline {
                if debug {
                    eprintln!(
                        "c [def] padoa deadline: round {}, defined {}, pending {}",
                        rounds,
                        defined.len(),
                        still.len()
                    );
                }
                // Return the partial split: Padoa is monotone (once a y
                // is provably defined under its links it stays defined),
                // and CEGAR handles an over-approximate `undefined` set
                // (those y's just get arbiter cells they didn't strictly
                // need). This preserves the work spent so far instead of
                // discarding it and falling through to SlotDpll. `still`
                // is a prefix of `todo` (the checked-not-defined ones);
                // append the unchecked suffix [y..] — disjoint by
                // construction since the loop iterates `todo` in order.
                still.extend(todo.iter().skip_while(|&&z| z != y).copied());
                return Some(DefSplit {
                    defined,
                    undefined: still,
                    n_const: n_prop_const,
                });
            }
            let dy = &deps[&y];
            let dyb = &dep_bits[&y];
            let mut assump: Vec<Lit> = Vec::with_capacity(2 + dy.len());
            assump.push(y as Lit);
            assump.push(-shift(y as Lit));
            for &u in dy {
                assump.push(sel[&u]);
            }
            for &z in &defined {
                if z != y && dep_bits.get(&z).map_or(true, |dz| is_sub(dz, dyb)) {
                    assump.push(sel[&z]);
                }
            }
            let sat = cdcl.solve(&assump, &mut model, budget_per);
            if cdcl.budget_hit {
                still.push(y);
                continue;
            }
            if sat {
                still.push(y);
            } else {
                defined.push(y);
                is_defined.insert(y);
                progress = true;
            }
        }
        todo = still;
        if !progress || todo.is_empty() {
            break;
        }
    }
    if debug {
        eprintln!(
            "c [def] padoa: {} rounds, {} defined, {} undefined",
            rounds,
            defined.len(),
            todo.len()
        );
    }
    Some(DefSplit {
        defined,
        undefined: todo,
        n_const: n_prop_const,
    })
}

/// For each `y` in `defined`, extract a McMillan interpolant `I(dep(y))`
/// such that `y ↔ I` under the matrix. One selector-gated CDCL is built
/// once; each y solves on a fresh *clone* of it so the proof is minimal
/// (sharing learned clauses across y's gave correct but bloated
/// interpolants — alu_add went 452→1001 gates and CEGAR doubled).
///
/// `undefined` are the Padoa-undef y's. They're *also* candidates: a
/// Padoa-undef y can still be unique given dep(y) ∪ {already-decided
/// undef-z}. (Padoa only links *defined*-z's, so a Tseitin gate over
/// other free e-vars — `y_t = T(y_{t-1}, U)` — is misclassified as
/// truly free.) The fixpoint promotes such y's to interpolated; the
/// undef-y's that remain free after the fixpoint are the *roots* the
/// CEGAR loop must search. Their cell count is what arbsolve has to
/// enumerate, so shrinking 138→5 collapses the round count.
///

/// Returns `(interpolants, roots)`. `roots ⊆ undefined`.
pub fn extract_interpolants(
    f: &Formula,
    defined: &[Var],
    undefined: &[Var],
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
) -> (HashMap<Var, Def>, Vec<Var>) {
    let n = f.n_vars as Lit;
    let m = f.clauses.len();
    let nu = n as Var;
    let shift = |l: Lit| -> Lit {
        if l > 0 {
            l + n
        } else {
            l - n
        }
    };
    let live: HashSet<Var> = f
        .clauses
        .iter()
        .flat_map(|c| c.iter().map(|&l| var(l)))
        .collect();
    let undef_set: HashSet<Var> = undefined.iter().copied().collect();
    let candidates: Vec<Var> = defined
        .iter()
        .chain(undefined.iter())
        .copied()
        .filter(|y| live.contains(y))
        .collect();
    let cand_set: HashSet<Var> = candidates.iter().copied().collect();
    // Clause-neighbor adjacency: y ~ z iff some clause contains both.
    // Used for VSIDS-style activity bumping — when y becomes linkable,
    // bump every undecided z it shares a clause with (z might now be
    // interpolatable using y as a link). This is the content-based
    // signal that replaces the var-id-as-unroll-order heuristic; see
    // `feedback_no_var_id_dep` and HISTORY iter116.
    let mut neighbors: HashMap<Var, Vec<Var>> =
        candidates.iter().map(|&y| (y, Vec::new())).collect();
    {
        let mut seen: HashSet<(Var, Var)> = HashSet::new();
        for c in &f.clauses {
            let cvs: Vec<Var> = c
                .iter()
                .map(|&l| var(l))
                .filter(|v| cand_set.contains(v))
                .collect();
            for i in 0..cvs.len() {
                for j in (i + 1)..cvs.len() {
                    let (a, b) = (cvs[i], cvs[j]);
                    if a != b && seen.insert((a.min(b), a.max(b))) {
                        neighbors.get_mut(&a).unwrap().push(b);
                        neighbors.get_mut(&b).unwrap().push(a);
                    }
                }
            }
        }
    }
    // Content-based deterministic tiebreak: hash of the dep set (lex
    // sorted). Two y's with identical content (same dep set, same
    // clause-neighbor structure) are interchangeable; this gives a
    // stable but ID-independent order between them.
    let dep_key: HashMap<Var, u64> = candidates
        .iter()
        .map(|&y| {
            let mut h: u64 = 0;
            for &d in &f.deps[&y] {
                h = h.wrapping_mul(0x100_0000_01B3).wrapping_add(d as u64);
            }
            (y, h)
        })
        .collect();

    // Bitset dep representation: the linkable-z subset check is
    // `O(|order|^2 × |U|)` over the fixpoint. With `BTreeSet::is_subset`
    // it walks both trees per check — 9.5% of the wall on
    // `pec_fifo1_n20` (2552 e-vars × 2552 candidate z's per pass).
    // Universal IDs index a bitset; the subset check is `(z & !y) == 0`.
    let nu_words = f.universals.len().div_ceil(64);
    let u_idx: HashMap<Var, usize> = f
        .universals
        .iter()
        .enumerate()
        .map(|(i, &u)| (u, i))
        .collect();
    let dep_bits: HashMap<Var, Vec<u64>> = f
        .deps
        .iter()
        .map(|(&y, d)| {
            let mut b = vec![0u64; nu_words];
            for &u in d {
                let i = u_idx[&u];
                b[i / 64] |= 1u64 << (i % 64);
            }
            (y, b)
        })
        .collect();
    let is_sub = |z: &[u64], y: &[u64]| z.iter().zip(y).all(|(&a, &b)| a & !b == 0);

    // Build a base CDCL once (copy-A | copy-B, no links) with
    // proof-logging enabled; per y, clone it and add only this y's link
    // clauses. Clone copies the already-built watch lists, which is
    // cheaper than `Cdcl::new` re-parsing 2m clause vecs and avoids the
    // selector indirection that bloats interpolants.
    let mut base_clauses: Vec<Clause> = Vec::with_capacity(2 * m);
    for c in &f.clauses {
        base_clauses.push(c.clone());
    }
    for c in &f.clauses {
        base_clauses.push(c.iter().map(|&l| shift(l)).collect());
    }
    let mut base = Cdcl::new(2 * n as usize, &base_clauses);
    base.enable_proof_log();
    let mut model = vec![0i8; 2 * n as usize + 1];
    // iter107: a shared selector-gated CDCL for the SAT/UNSAT *test*.
    // Cloning `base` per-y was ~50KB arena + ~100KB watches × 2134 y's
    // × multiple passes — the memory traffic dominated the wall on
    // pec_alu_add_n8. The shared CDCL has one selector per linkable var
    // (universal or existential): `s_v → (v ↔ v')`. Per-y, assume the
    // selectors for `dep(y) ∪ linked_z` and `[y, ¬y']`. No proof log on
    // the shared instance — when the shared solve is UNSAT, clone `base`
    // (proof-logged, no selectors → minimal proof) and re-solve with the
    // *winning* link set to extract the interpolant. The retry cost is
    // O(|defined|) clones instead of O(|order| × passes).
    //
    // Sound: the shared CDCL's clauses are `f.clauses ∪ shifted ∪ {s_v →
    // v↔v'}`; assuming a subset of selectors makes the *active* link set
    // a subset, and a SAT model under fewer constraints is also a model
    // under no constraints — so SAT/UNSAT decisions are exact.
    let link_vars2: Vec<Var> = {
        let mut v: Vec<Var> = f.universals.iter().copied().collect();
        v.extend(f.deps.keys().copied());
        v.sort_unstable();
        v
    };
    let sel_base = 2 * n as Lit;
    let sel2: HashMap<Var, Lit> = link_vars2
        .iter()
        .enumerate()
        .map(|(i, &v)| (v, sel_base + 1 + i as Lit))
        .collect();
    let total2 = 2 * n as usize + link_vars2.len();
    let mut shared_clauses = base_clauses.clone();
    for &v in &link_vars2 {
        let s = sel2[&v];
        let (a, b) = (v as Lit, shift(v as Lit));
        shared_clauses.push(vec![-s, -a, b]);
        shared_clauses.push(vec![-s, a, -b]);
    }
    let mut shared = Cdcl::new(total2, &shared_clauses);
    let mut shared_model = vec![0i8; total2 + 1];

    let mut out: HashMap<Var, Def> = HashMap::new();
    // iter106: unit-propagated existentials get a constant interpolant
    // directly (`root` ∈ {0,1}). No 2-copy CDCL clone, no McMillan, no
    // budget. They're already in `defined` (the Padoa pre-filter); this
    // just shortcuts the interpolation. Constants are trivially
    // dep(y)-functions so they can be linked by every later y.
    let prop = unit_prop_constants(f);
    let mut n_const = 0usize;
    for &y in defined {
        if !live.contains(&y) || prop[y as usize] == 0 {
            continue;
        }
        let root = if prop[y as usize] > 0 { 1 } else { 0 };
        out.insert(
            y,
            Def {
                itp: Itp::new(),
                root,
            },
        );
        n_const += 1;
    }
    if debug && n_const > 0 {
        eprintln!("c [def] {} constant interpolants from unit-prop", n_const);
    }
    // Linkable z's: interpolated y's *and* free roots. Both are decided
    // — their Skolem function is known (an interpolant or the cell
    // table) — so subsequent y's can be unique-given-them. Roots come
    // first in `linkable` because they have the smallest dep (sort
    // order) and are processed first.
    let mut linkable: Vec<Var> = out.keys().copied().collect();
    // y's already processed in this fixpoint with no progress possible:
    // - undef-y that came back SAT given current links → free root.
    //   It's *added* to `linkable` (others can reference it) but marked
    //   `decided` so it's never re-processed (re-processing could find
    //   it unique given a *later*-processed root → cycle in the cert).
    // - any y the budget hit — re-trying every pass burns the deadline.
    let mut decided: HashSet<Var> = HashSet::new();
    let mut roots: Vec<Var> = Vec::new();
    // ---- VSIDS-style adaptive worklist (iter116) -----------------------
    // Replaces the static `(|dep|, var-id)` sort: var-id encoded the
    // BMC-unrolling step order for our generators, an unstated contract
    // that breaks on a non-conforming encoder (`scripts/revid.py` →
    // 24 roots vs 15 on `updown_n4_k008`). The worklist is content-driven:
    //
    //   activity[y] = #linkable clause-neighbors (signal: y can use them
    //                 as interpolation links → likely interpolatable).
    //   tiebreak    = (|dep(y)|, dep-set hash) — content, not var-id.
    //
    // - A successful interpolation bumps every undecided clause-neighbor
    //   (the new linkable z opens a path).
    // - A SAT-y (not interpolatable with the current links) is *deferred*,
    //   not promoted to root immediately. It re-enters the queue at its
    //   current activity; if a neighbor later becomes linkable, the bump
    //   gives it another shot before any root promotion.
    // - On deadlock (queue drained, no progress, some y's pending):
    //   promote the pending undef-y with the *lowest* activity to root —
    //   it has the fewest linkable neighbors, so it's the most likely to
    //   be a true root rather than a chain link waiting on a predecessor.
    //   Bump its neighbors and retry.
    //
    // Convergence: O(roots) deadlock rounds × O(|candidates|) tries. For
    // a chain that bootstraps from constants (the BMC succinct case)
    // there is no deadlock and the bump propagation finishes in one round
    // regardless of processing order.
    // Pending: candidates not yet decided.
    let mut pending: Vec<Var> = candidates
        .iter()
        .copied()
        .filter(|y| !out.contains_key(y) && !decided.contains(y))
        .collect();
    // `last_failed_at[y]` records the linkable-set size at which `y`
    // last failed. Skip `y` in the next round if the set hasn't grown.
    let mut last_failed_at: HashMap<Var, usize> = HashMap::new();
    // Conflict-directed activity (VSIDS): when `y` fails (SAT), the
    // 2-copy SAT model gives an assignment where `y_A ≠ y_B`. Every
    // clause-neighbor `z` that *also* differs (`z_A ≠ z_B`) is a
    // "blocker" for `y` — linking `z` would break the symmetry and let
    // `y` interpolate. Bump every blocker; process highest-activity
    // first. Geometric decay so old conflicts age out. This is the
    // content-derived signal Markus asked for ("heuristics like
    // VSIDS"); it replaces the var-id-as-unroll-order heuristic. See
    // `feedback_no_var_id_dep` and HISTORY iter116.
    let mut conflict_act: HashMap<Var, f64> = candidates.iter().map(|&y| (y, 0.0)).collect();
    let mut conflict_inc: f64 = 1.0;
    const CONFLICT_DECAY: f64 = 1.05;
    let mut n_rounds = 0usize;
    let mut n_bumps = 0usize;
    'rounds: loop {
        n_rounds += 1;
        if start.elapsed().as_secs_f64() >= deadline {
            break;
        }
        pending.retain(|y| !out.contains_key(y) && !decided.contains(y));
        if pending.is_empty() {
            break;
        }
        // Sort: conflict activity (desc), then |dep| (asc), dep hash,
        // var-id (deterministic last resort).
        let act_q: HashMap<Var, u64> = pending
            .iter()
            .map(|&y| (y, (conflict_act[&y] * 1024.0) as u64))
            .collect();
        pending.sort_by_key(|&y| (u64::MAX - act_q[&y], f.deps[&y].len(), dep_key[&y], y));
        let mut progress = false;
        for &y in &pending.clone() {
            if out.contains_key(&y) || decided.contains(&y) {
                continue;
            }
            if start.elapsed().as_secs_f64() >= deadline {
                break 'rounds;
            }
            let dy: BTreeSet<Var> = f.deps[&y].clone();
            let dyb = &dep_bits[&y];
            let linked_z: Vec<Var> = linkable
                .iter()
                .copied()
                .filter(|&z| z != y && is_sub(&dep_bits[&z], dyb))
                .collect();
            // Skip if the *relevant* link set hasn't grown since last
            // failure. The linkable set always grows, but `y` only
            // benefits from new z's with `dep(z) ⊆ dep(y)` — that's what
            // `linked_z` captures. Without this, every pending y is
            // re-solved every round (O(|cand| × rounds) tries, ~50× the
            // work the static sort needs for a chain).
            if last_failed_at.get(&y).is_some_and(|&l| l >= linked_z.len()) {
                continue;
            }
            // Test on the shared CDCL (no proof log, no clone).
            let mut sh_assump: Vec<Lit> = vec![y as Lit, -shift(y as Lit)];
            for &u in dy.iter().chain(linked_z.iter()) {
                sh_assump.push(sel2[&u]);
            }
            let sh_sat = shared.solve(&sh_assump, &mut shared_model, 50_000);
            if !shared.budget_hit && sh_sat {
                // SAT — not interpolatable. Bump the blockers.
                for &z in neighbors.get(&y).map(|v| v.as_slice()).unwrap_or(&[]) {
                    if out.contains_key(&z) || decided.contains(&z) {
                        continue;
                    }
                    let za = shared_model[z as usize];
                    let zb = shared_model[shift(z as Lit).unsigned_abs() as usize];
                    if za != 0 && zb != 0 && za != zb {
                        *conflict_act.get_mut(&z).unwrap() += conflict_inc;
                        n_bumps += 1;
                    }
                }
                conflict_inc *= CONFLICT_DECAY;
                if conflict_inc > 1e30 {
                    for v in conflict_act.values_mut() {
                        *v /= conflict_inc;
                    }
                    conflict_inc = 1.0;
                }
                last_failed_at.insert(y, linked_z.len());
                continue;
            }
            // UNSAT (or shared budget-hit): re-solve with proof log.
            let mut cdcl = base.clone();
            for &u in dy.iter().chain(linked_z.iter()) {
                let (a, b) = (u as Lit, shift(u as Lit));
                cdcl.add_external(&[-a, b]);
                cdcl.add_external(&[a, -b]);
            }
            let unsat = !cdcl.solve(&[y as Lit, -shift(y as Lit)], &mut model, 50_000);
            if cdcl.budget_hit {
                last_failed_at.insert(y, linked_z.len());
                continue;
            }
            if !unsat {
                // Same conflict-directed bump (clone confirmed SAT).
                for &z in neighbors.get(&y).map(|v| v.as_slice()).unwrap_or(&[]) {
                    if out.contains_key(&z) || decided.contains(&z) {
                        continue;
                    }
                    let za = model[z as usize];
                    let zb = model[shift(z as Lit).unsigned_abs() as usize];
                    if za != 0 && zb != 0 && za != zb {
                        *conflict_act.get_mut(&z).unwrap() += conflict_inc;
                    }
                }
                conflict_inc *= CONFLICT_DECAY;
                last_failed_at.insert(y, linked_z.len());
                continue;
            }
            let sharedv: HashSet<Var> = dy.iter().chain(linked_z.iter()).copied().collect();
            let side = |cr: u32| -> Side {
                if cdcl.clause_lits(cr).iter().all(|&l| var(l) <= nu) {
                    Side::A
                } else {
                    Side::B
                }
            };
            let a_local = |v: Var| v <= nu && !sharedv.contains(&v);
            let became_linkable =
                if let Some((itp, root)) = mcmillan(&cdcl, side, &sharedv, a_local) {
                    out.insert(y, Def { itp, root });
                    linkable.push(y);
                    true
                } else if undef_set.contains(&y) {
                    decided.insert(y);
                    roots.push(y);
                    linkable.push(y);
                    true
                } else {
                    false
                };
            if became_linkable {
                progress = true;
                last_failed_at.remove(&y);
            }
        }
        if progress {
            continue;
        }
        // Deadlock: nothing interpolated this round and the pending set
        // is non-empty. Promote the *highest*-activity pending undef-y
        // to root: it was the most-frequent blocker across all the SAT
        // models this round, so making it a root unblocks the most
        // other y's and fastest collapses the chain. Content tiebreaks
        // (|dep|, dep hash, var-id last).
        let next_root = pending
            .iter()
            .copied()
            .filter(|y| !out.contains_key(y) && !decided.contains(y) && undef_set.contains(y))
            .max_by_key(|&y| {
                (
                    (conflict_act[&y] * 1024.0) as u64,
                    std::cmp::Reverse((f.deps[&y].len(), dep_key[&y], y)),
                )
            });
        match next_root {
            None => break,
            Some(y) => {
                decided.insert(y);
                roots.push(y);
                linkable.push(y);
                last_failed_at.remove(&y);
            }
        }
    }
    if debug {
        eprintln!(
            "c [def] worklist: {} rounds, {} blocker bumps, {} interp, {} roots",
            n_rounds,
            n_bumps,
            out.len(),
            roots.len()
        );
    }
    // Padoa-undef y's never reached (deadline) are roots — sound,
    // because the cell arbiter is a fallback for any free y.
    for &y in undefined {
        if live.contains(&y) && !out.contains_key(&y) && !decided.contains(&y) {
            roots.push(y);
        }
    }
    if debug {
        eprintln!(
            "c [def] interpolants: {}/{} defined + {}/{} undef→linked (gates: {}, roots {})",
            out.values().filter(|_| true).count()
                - undefined.iter().filter(|y| out.contains_key(y)).count(),
            defined.len(),
            undefined.iter().filter(|y| out.contains_key(y)).count(),
            undefined.len(),
            out.values().map(|d| d.itp.gates.len()).sum::<usize>(),
            roots.len(),
        );
    }
    (out, roots)
}

/// Cross-check each interpolant against the matrix at `k` random rows.
pub fn validate_interpolants(
    f: &Formula,
    defs: &HashMap<Var, Def>,
    k: usize,
) -> Option<(Var, Vec<Lit>)> {
    let n = f.n_vars as usize;
    let mut cdcl = Cdcl::new(n, &f.clauses);
    let mut model = vec![0i8; n + 1];
    // Evaluate all interpolants at row `urow` (recursive over linked-z).
    fn eval_at(
        y: Var,
        urow: &HashMap<Var, bool>,
        defs: &HashMap<Var, Def>,
        memo: &mut HashMap<Var, bool>,
    ) -> Option<bool> {
        if let Some(&v) = memo.get(&y) {
            return Some(v);
        }
        let d = defs.get(&y)?;
        let mut a = 0u64;
        for (i, &v) in d.itp.inputs.iter().enumerate() {
            let bit = if let Some(&b) = urow.get(&v) {
                b
            } else {
                eval_at(v, urow, defs, memo)?
            };
            if bit {
                a |= 1 << i;
            }
        }
        let r = d.itp.eval(d.root, a);
        memo.insert(y, r);
        Some(r)
    }
    let mut seed = 0x5eed_u64;
    for _ in 0..k {
        seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
        let urow: HashMap<Var, bool> = f
            .universals
            .iter()
            .enumerate()
            .map(|(i, &u)| (u, (seed >> (i % 60)) & 1 == 1))
            .collect();
        let assump: Vec<Lit> = urow
            .iter()
            .map(|(&u, &b)| if b { u as Lit } else { -(u as Lit) })
            .collect();
        if !cdcl.solve(&assump, &mut model, 100_000) {
            continue;
        }
        let mut memo = HashMap::new();
        // Check in dependency order so the first mismatch is the root cause.
        let mut order: Vec<Var> = defs.keys().copied().collect();
        order.sort_by_key(|y| f.deps[y].len());
        for &y in &order {
            // First check inputs are consistent (so we report the *root*).
            let d = &defs[&y];
            let mut ok = true;
            for &v in &d.itp.inputs {
                if defs.contains_key(&v) {
                    if let Some(iv) = eval_at(v, &urow, defs, &mut memo) {
                        if iv != (model[v as usize] > 0) {
                            ok = false;
                        }
                    }
                }
            }
            if !ok {
                continue;
            }
            if let Some(iv) = eval_at(y, &urow, defs, &mut memo) {
                let mv = model[y as usize] > 0;
                if iv != mv {
                    eprintln!(
                        "  validate: y={} itp={} model={} inputs_mv={:?}",
                        y,
                        iv,
                        mv,
                        d.itp
                            .inputs
                            .iter()
                            .map(|&v| (v, model[v as usize]))
                            .collect::<Vec<_>>()
                    );
                    return Some((y, assump));
                }
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn build(us: &[Var], deps: &[(Var, &[Var])], cls: &[&[Lit]]) -> Formula {
        Formula::new(
            us.iter()
                .chain(deps.iter().map(|(v, _)| v))
                .copied()
                .max()
                .unwrap_or(0),
            us.to_vec(),
            deps.iter()
                .map(|&(e, d)| (e, d.iter().copied().collect()))
                .collect(),
            cls.iter().map(|c| c.to_vec()).collect(),
        )
    }

    #[test]
    fn interpolant_buffer() {
        // ∀u ∃y(u): (¬u∨y)(u∨¬y)  ⟹  y ↔ u.
        let f = build(&[1], &[(2, &[1])], &[&[-1, 2], &[1, -2]]);
        let start = std::time::Instant::now();
        let defs = extract_interpolants(&f, &[2], &[], 5.0, &start, false).0;
        let d = &defs[&2];
        assert_eq!(d.itp.inputs, vec![1]);
        // y ↔ u: at u=0 → y=0; u=1 → y=1.
        assert_eq!(d.itp.eval(d.root, 0b0), false);
        assert_eq!(d.itp.eval(d.root, 0b1), true);
    }

    #[test]
    fn interpolant_and() {
        // ∀u₁u₂ ∃y(u₁,u₂): y ↔ u₁∧u₂.
        let f = build(
            &[1, 2],
            &[(3, &[1, 2])],
            &[&[-1, -2, 3], &[1, -3], &[2, -3]],
        );
        let start = std::time::Instant::now();
        let defs = extract_interpolants(&f, &[3], &[], 5.0, &start, false).0;
        let d = &defs[&3];
        // Find input order
        let i1 = d.itp.inputs.iter().position(|&v| v == 1).unwrap();
        let i2 = d.itp.inputs.iter().position(|&v| v == 2).unwrap();
        for u1 in 0..2u64 {
            for u2 in 0..2u64 {
                let a = (u1 << i1) | (u2 << i2);
                assert_eq!(
                    d.itp.eval(d.root, a),
                    u1 == 1 && u2 == 1,
                    "u1={} u2={}",
                    u1,
                    u2
                );
            }
        }
    }

    #[test]
    fn interpolant_xor() {
        // y ↔ u₁⊕u₂ (4 clauses).
        let f = build(
            &[1, 2],
            &[(3, &[1, 2])],
            &[&[-1, -2, -3], &[-1, 2, 3], &[1, -2, 3], &[1, 2, -3]],
        );
        let start = std::time::Instant::now();
        let defs = extract_interpolants(&f, &[3], &[], 5.0, &start, false).0;
        let d = &defs[&3];
        let i1 = d.itp.inputs.iter().position(|&v| v == 1).unwrap();
        let i2 = d.itp.inputs.iter().position(|&v| v == 2).unwrap();
        for u1 in 0..2u64 {
            for u2 in 0..2u64 {
                let a = (u1 << i1) | (u2 << i2);
                assert_eq!(d.itp.eval(d.root, a), u1 != u2);
            }
        }
    }
}

#[test]
#[ignore]
fn interpolant_validate_pec() {
    let path =
        "../../benchmarks/train/pec_circuits/miter/pec_alu_add_n4_k2_bb3_complete.dqdimacs.gz";
    let buf = String::from_utf8(
        std::process::Command::new("gzip")
            .args(["-dc", path])
            .output()
            .unwrap()
            .stdout,
    )
    .unwrap();
    let f = crate::parse::parse(&buf).expect("parse");
    let start = std::time::Instant::now();
    let split = padoa_split(&f, 5.0, &start, false).expect("padoa");
    let defs = extract_interpolants(&f, &split.defined, &split.undefined, 30.0, &start, false).0;
    assert!(validate_interpolants(&f, &defs, 20).is_none());
}

#[allow(dead_code)]
#[cfg(any())]
fn _old_e179_debug() {
    let path =
        "../../benchmarks/train/pec_circuits/miter/pec_alu_add_n4_k2_bb3_complete.dqdimacs.gz";
    let buf = String::from_utf8(
        std::process::Command::new("gzip")
            .args(["-dc", path])
            .output()
            .unwrap()
            .stdout,
    )
    .unwrap();
    let f = crate::parse::parse(&buf).expect("parse");
    let start = std::time::Instant::now();
    let split = padoa_split(&f, 5.0, &start, false).expect("padoa");
    let defs = extract_interpolants(&f, &split.defined, &split.undefined, 30.0, &start, false).0;
    eprintln!("e179 in defined: {}", split.defined.contains(&179));
    eprintln!("e179 has interpolant: {}", defs.contains_key(&179));
    // Which z's would Padoa link for e179?
    let dy: BTreeSet<Var> = f.deps[&179].clone();
    let pad_linked: Vec<Var> = split
        .defined
        .iter()
        .copied()
        .filter(|z| *z != 179 && f.deps[z].is_subset(&dy))
        .collect();
    eprintln!("Padoa would link {} z's for e179", pad_linked.len());
    // How many of those are in defs (interpolated before e179)?
    let itp_linked: Vec<Var> = pad_linked
        .iter()
        .copied()
        .filter(|z| defs.contains_key(z))
        .collect();
    eprintln!("  of which {} are interpolated", itp_linked.len());
    // The non-interpolated linked z's:
    let missing: Vec<Var> = pad_linked
        .iter()
        .copied()
        .filter(|z| !defs.contains_key(z))
        .collect();
    eprintln!("  missing: {:?}", &missing[..missing.len().min(10)]);
    // Manual: build the per-y CDCL with ALL pad_linked z's, see if UNSAT.
    let n = f.n_vars as Lit;
    let shift = |l: Lit| if l > 0 { l + n } else { l - n };
    let mut clauses: Vec<Clause> = Vec::new();
    for c in &f.clauses {
        clauses.push(c.clone());
    }
    for c in &f.clauses {
        clauses.push(c.iter().map(|&l| shift(l)).collect());
    }
    for &u in dy.iter().chain(pad_linked.iter()) {
        clauses.push(vec![-(u as Lit), shift(u as Lit)]);
        clauses.push(vec![u as Lit, -shift(u as Lit)]);
    }
    let mut cdcl = Cdcl::new(2 * n as usize, &clauses);
    let mut model = vec![0i8; 2 * n as usize + 1];
    let unsat = !cdcl.solve(&[179, -shift(179)], &mut model, 100_000);
    eprintln!(
        "with all pad_linked z's: unsat={} budget_hit={}",
        unsat, cdcl.budget_hit
    );
    // Dump e46's full proof + interpolant.
    std::env::set_var("FRUST_ITP_TRACE", "1");
    {
        let n = f.n_vars as Lit;
        let shift = |l: Lit| if l > 0 { l + n } else { l - n };
        let dy: BTreeSet<Var> = f.deps[&46].clone();
        let linked_z: Vec<Var> = vec![40, 43, 44]; // from observed inputs
        let mut clauses: Vec<Clause> = Vec::new();
        for c in &f.clauses {
            clauses.push(c.clone());
        }
        for c in &f.clauses {
            clauses.push(c.iter().map(|&l| shift(l)).collect());
        }
        for &u in dy.iter().chain(linked_z.iter()) {
            clauses.push(vec![-(u as Lit), shift(u as Lit)]);
            clauses.push(vec![u as Lit, -shift(u as Lit)]);
        }
        let mut cdcl = Cdcl::new(2 * n as usize, &clauses);
        cdcl.enable_proof_log();
        let mut model = vec![0i8; 2 * n as usize + 1];
        let unsat = !cdcl.solve(&[46, -shift(46)], &mut model, 100_000);
        eprintln!("e46 proof: unsat={}", unsat);
        let pl = cdcl.proof.as_ref().unwrap();
        eprintln!("  final_clause={:?}", pl.final_clause);
        eprintln!("  final_chain.len={}", pl.final_chain.len());
        for &(cr, piv) in &pl.final_chain {
            let lits = cdcl.clause_lits(cr);
            let learned = pl.ante.contains_key(&cr);
            eprintln!(
                "    cr={} piv={} lits={:?} learned={}",
                cr, piv, lits, learned
            );
        }
        // Now run mcmillan with trace.
        let nu = n as Var;
        let shared: HashSet<Var> = dy.iter().chain(linked_z.iter()).copied().collect();
        let side = |cr: u32| {
            if cdcl.clause_lits(cr).iter().all(|&l| var(l) <= nu) {
                crate::interpolant::Side::A
            } else {
                crate::interpolant::Side::B
            }
        };
        let a_local = |v: Var| v <= nu && !shared.contains(&v);
        let (itp, root) = mcmillan(&cdcl, side, &shared, a_local).unwrap();
        eprintln!(
            "e46 interpolant: inputs={:?} gates={:?} root={}",
            itp.inputs, itp.gates, root
        );
    }
    std::env::remove_var("FRUST_ITP_TRACE");
    // Validate all interpolants
    let bad = validate_interpolants(&f, &defs, 20);
    match bad {
        None => eprintln!("all interpolants validate at 20 random rows"),
        Some((y, row)) => {
            eprintln!("MISMATCH: y={} at row {:?}", y, &row[..row.len().min(8)]);
            let d = &defs[&y];
            eprintln!(
                "  inputs={:?} gates={} root={}",
                d.itp.inputs,
                d.itp.gates.len(),
                d.root
            );
            for (i, g) in d.itp.gates.iter().enumerate() {
                eprintln!("  g{}: {:?}", i, g);
            }
        }
    }
}

#[test]
#[ignore] // bench-scale; run with --ignored
fn interpolant_pec_sample() {
    let path =
        "../../benchmarks/train/pec_circuits/miter/pec_alu_add_n4_k2_bb3_complete.dqdimacs.gz";
    let buf = String::from_utf8(
        std::process::Command::new("gzip")
            .args(["-dc", path])
            .output()
            .unwrap()
            .stdout,
    )
    .unwrap();
    let f = crate::parse::parse(&buf).expect("parse");
    let start = std::time::Instant::now();
    let split = padoa_split(&f, 5.0, &start, false).expect("padoa");
    eprintln!(
        "padoa: {} defined, {} undef ({:.2}s)",
        split.defined.len(),
        split.undefined.len(),
        start.elapsed().as_secs_f64()
    );
    let t1 = std::time::Instant::now();
    let defs = extract_interpolants(&f, &split.defined, &split.undefined, 30.0, &start, true).0;
    let mut sizes: Vec<usize> = defs.values().map(|d| d.itp.gates.len()).collect();
    sizes.sort_unstable();
    eprintln!(
        "interpolants: {}/{} in {:.2}s; gate sizes min/med/max = {}/{}/{}",
        defs.len(),
        split.defined.len(),
        t1.elapsed().as_secs_f64(),
        sizes.first().copied().unwrap_or(0),
        sizes.get(sizes.len() / 2).copied().unwrap_or(0),
        sizes.last().copied().unwrap_or(0)
    );
}
