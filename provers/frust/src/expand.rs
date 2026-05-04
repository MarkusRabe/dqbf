//! Universal expansion + slot search for |U| ≤ MAX_U.
//!
//! Free pass: solve each of the 2^|U| rows under universals-only
//! assumptions with one persistent CDCL. If any row is genuinely UNSAT
//! → DQBF UNSAT (caller emits the verdict). Otherwise record per-
//! (existential, dep-key) the first model value and the slot set =
//! {(i,k) : two rows disagreed}. If no slots, the free pass is a valid
//! Skolem. Otherwise DPLL over slot values: pin slots, re-solve rows,
//! check the resulting tables are consistent; on row-UNSAT prune, on
//! greedy-fill conflict decide more, on full exhaust grow the slot set
//! by the new conflicts and retry (≤5 rounds). Only emits SAT — the
//! cert is independently checkable.

use crate::aiger::Skolem;
use crate::cdcl::Cdcl;
use crate::formula::{Formula, Lit, Var};
use std::collections::HashMap;

pub const MAX_U: usize = 20;
const PARTIAL_U: usize = 16; // partial-mode (UNSAT-only) scan width

macro_rules! dbg_ex {
    ($d:expr, $($a:tt)*) => { if $d { eprintln!("c [expand] {}", format!($($a)*)); } }
}

/// Select which universals to enumerate. If |U| ≤ MAX_U, all of them.
/// Otherwise the MAX_U with highest clause occurrence — enumerating
/// those gives the best chance of an UNSAT-row witness.
fn pick_expand_universals(f: &Formula) -> Vec<Var> {
    if f.universals.len() <= MAX_U {
        return f.universals.clone();
    }
    let mut occ: HashMap<Var, u32> = HashMap::new();
    for c in &f.clauses {
        for &l in c {
            let v = l.unsigned_abs();
            if f.is_universal(v) {
                *occ.entry(v).or_default() += 1;
            }
        }
    }
    let mut us = f.universals.clone();
    us.sort_by_key(|u| std::cmp::Reverse(occ.get(u).copied().unwrap_or(0)));
    us.truncate(PARTIAL_U);
    us.sort_unstable();
    us
}

pub fn try_expand(
    f: &Formula,
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
    unsat_row: &mut Option<u32>,
) -> Option<Skolem> {
    let nu_full = f.universals.len();
    let expand_us = pick_expand_universals(f);
    let nu = expand_us.len();
    let partial = nu < nu_full;
    if partial {
        dbg_ex!(
            debug,
            "partial: |U|={} > MAX_U={}, enumerating {} (UNSAT-only)",
            nu_full,
            MAX_U,
            nu
        );
    }
    dbg_ex!(
        debug,
        "|U|={} ({} rows), |E|={}, |C|={}",
        nu,
        1u32 << nu,
        f.deps.len(),
        f.clauses.len()
    );
    let n = f.n_vars as usize + 1;
    let mut cdcl = Cdcl::new(f.n_vars as usize, &f.clauses);
    let mut model = vec![0i8; n];
    let exs: Vec<Var> = f.deps.keys().copied().collect();
    let u_idx: HashMap<Var, usize> = expand_us.iter().enumerate().map(|(i, &u)| (u, i)).collect();
    // dep_lists / dep_mask only over the *expanded* universals; in partial
    // mode the unselected ones are treated as free CDCL variables.
    let dep_lists: Vec<Vec<Var>> = exs
        .iter()
        .map(|y| {
            f.deps[y]
                .iter()
                .copied()
                .filter(|d| u_idx.contains_key(d))
                .collect()
        })
        .collect();
    let dep_mask: Vec<u32> = dep_lists
        .iter()
        .map(|ds| ds.iter().map(|d| 1u32 << u_idx[d]).sum())
        .collect();
    let rows = 1u32 << nu;
    let row_budget: u64 = ((1_000_000 / rows.max(1)) as u64).max(100);
    let full_mask = (1u32 << nu).wrapping_sub(1);
    let row_assumps = |ub: u32, extra: &[(Var, i8)]| -> Vec<Lit> {
        let mut a: Vec<Lit> = expand_us
            .iter()
            .enumerate()
            .map(|(i, &u)| {
                if (ub >> i) & 1 == 1 {
                    u as Lit
                } else {
                    -(u as Lit)
                }
            })
            .collect();
        for &(y, v) in extra {
            if v != 0 {
                a.push(if v > 0 { y as Lit } else { -(y as Lit) });
            }
        }
        a
    };

    // CEGAR over the dep-∅ existentials ("outer" / constants). Complete
    // for ∃∀∃ shape with full enumeration (16<|U|≤MAX_U); UNSAT-only when
    // partial or when mixed-dep exs exist (SAT would need cross-row
    // consistency for those, which CEGAR doesn't track).
    let outer: Vec<usize> = (0..exs.len())
        .filter(|&i| f.deps[&exs[i]].is_empty())
        .collect();
    let eae = dep_mask.iter().all(|&m| m == 0 || m == full_mask);
    let cegar_full = !partial && nu > 16 && eae && !outer.is_empty();
    let cegar_unsat_only = partial && !outer.is_empty();
    if cegar_full || cegar_unsat_only {
        return outer_cegar(
            &mut cdcl,
            &exs,
            &dep_lists,
            &dep_mask,
            &outer,
            n,
            rows,
            &row_assumps,
            row_budget,
            deadline * 0.9,
            start,
            debug,
            unsat_row,
            cegar_unsat_only,
        );
    }

    // ---- Free pass: solve every row free; record first value per
    // (existential, dep-key) and the set of (i,k) pairs that disagreed.
    let mut first_seen: Vec<Vec<i8>> = (0..exs.len())
        .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
        .collect();
    let mut slots: Vec<(usize, usize)> = Vec::new();
    let mut in_slot: std::collections::HashSet<(usize, usize)> = std::collections::HashSet::new();
    for ub in 0..rows {
        if start.elapsed().as_secs_f64() > deadline * 0.4 {
            return None;
        }
        cdcl.reset_phase();
        let assumps = row_assumps(ub, &[]);
        if !cdcl.solve(&assumps, &mut model, row_budget) {
            dbg_ex!(debug, "free pass row {}: UNSAT/budget", ub);
            if !cdcl.budget_hit {
                // Sound even in partial mode: UNSAT under X'=x' (X\X' free)
                // means ∀(X\X', Y) violate, so any x_rest is a witness.
                *unsat_row = Some(ub);
            }
            return None;
        }
        if partial {
            // Can't build a Skolem from partial enumeration; just keep
            // scanning for an UNSAT row.
            continue;
        }
        for (i, &y) in exs.iter().enumerate() {
            let key = extract(ub, dep_mask[i]) as usize;
            let v: i8 = if model[y as usize] > 0 { 1 } else { -1 };
            if first_seen[i][key] == 0 {
                first_seen[i][key] = v;
            } else if first_seen[i][key] != v && in_slot.insert((i, key)) {
                slots.push((i, key));
            }
        }
    }
    dbg_ex!(
        debug,
        "free pass {:.2}s; {} slots; row_budget={}",
        start.elapsed().as_secs_f64(),
        slots.len(),
        row_budget
    );
    if partial {
        dbg_ex!(debug, "partial: all 2^{} rows SAT, no UNSAT witness", nu);
        return None; // saturation handles SAT
    }
    if slots.is_empty() {
        // No conflicts: the free pass IS a consistent Skolem.
        return Some(build_skolem(&exs, &dep_lists, &first_seen));
    }
    // Batch mode: at high row counts, decide-all-then-check (1 row-scan
    // per leaf) beats incremental (1 row-scan per slot).
    let batch = rows > (1 << 16);
    let dpll_cap = if batch { 0.9 } else { 0.5 };

    let mut tables: Vec<Vec<i8>> = (0..exs.len())
        .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
        .collect();
    let mut pins: Vec<(Var, i8)> = Vec::new();
    let mut cegar_round = 0;
    'cegar: loop {
        cegar_round += 1;
        dbg_ex!(
            debug,
            "slot-DPLL round {}: {} slots",
            cegar_round,
            slots.len()
        );
        // Precompute: for each row, which slots are pinned in it.
        let row_slots: Vec<Vec<usize>> = (0..rows)
            .map(|ub| {
                slots
                    .iter()
                    .enumerate()
                    .filter(|&(_, &(i, k))| extract(ub, dep_mask[i]) as usize == k)
                    .map(|(p, _)| p)
                    .collect()
            })
            .collect();
        let mut slot_val: Vec<i8> = vec![0; slots.len()];
        let mut decisions: Vec<(usize, bool)> = Vec::new(); // (slot_idx, flipped)
        let mut next_slot = 0usize;
        let mut iters = 0u64;
        let mut new_conflicts: std::collections::HashSet<(usize, usize)> =
            std::collections::HashSet::new();
        loop {
            iters += 1;
            if iters & 0x3f == 0 && start.elapsed().as_secs_f64() > deadline * dpll_cap {
                return None;
            }
            // Decide one slot at a time so CDCL-UNSAT can prune subtrees.
            // At |U|>16 the row-scan dominates, so batch-decide instead.
            while next_slot < slots.len() {
                let (i, k) = slots[next_slot];
                slot_val[next_slot] = first_seen[i][k]; // prefer first-seen value
                decisions.push((next_slot, false));
                next_slot += 1;
                if !batch {
                    break;
                }
            }
            let all_decided = next_slot >= slots.len();
            // Run all rows with current slot assignment + greedy fill.
            for t in tables.iter_mut() {
                t.fill(0);
            }
            for (p, &(i, k)) in slots.iter().enumerate() {
                tables[i][k] = slot_val[p];
            }
            let mut prune = false; // CDCL-UNSAT under slot pins → backtrack
            let mut soft_conflict = false; // greedy-fill disagree → decide more
            for ub in 0..rows {
                if batch && ub & 0x3fff == 0 && start.elapsed().as_secs_f64() > deadline * dpll_cap
                {
                    return None;
                }
                pins.clear();
                for &p in &row_slots[ub as usize] {
                    if slot_val[p] != 0 {
                        pins.push((exs[slots[p].0], slot_val[p]));
                    }
                }
                if !batch {
                    cdcl.reset_phase();
                }
                let assumps = row_assumps(ub, &pins);
                if !cdcl.solve(&assumps, &mut model, row_budget) {
                    prune = true;
                    break;
                }
                for (i, &y) in exs.iter().enumerate() {
                    let key = extract(ub, dep_mask[i]) as usize;
                    let v: i8 = if model[y as usize] > 0 { 1 } else { -1 };
                    if tables[i][key] == 0 {
                        tables[i][key] = v;
                    } else if tables[i][key] != v {
                        soft_conflict = true;
                        new_conflicts.insert((i, key));
                    }
                }
            }
            if !prune && !soft_conflict {
                dbg_ex!(
                    debug,
                    "slot-DPLL: SAT after {} iters, {} learned",
                    iters,
                    cdcl.n_learned
                );
                return Some(build_skolem(&exs, &dep_lists, &tables));
            }
            if !prune && !all_decided {
                // soft conflict but more slots to decide — keep going.
                continue;
            }
            // Backtrack (prune, or soft_conflict at a leaf).
            loop {
                let (si, flipped) = match decisions.pop() {
                    Some(d) => d,
                    None => {
                        dbg_ex!(
                            debug,
                            "slot-DPLL exhausted after {} iters; {} new conflicts; cdcl {} learned",
                            iters,
                            new_conflicts.len(),
                            cdcl.n_learned
                        );
                        let added: Vec<_> = new_conflicts
                            .iter()
                            .filter(|s| !in_slot.contains(s))
                            .copied()
                            .collect();
                        if added.is_empty()
                            || cegar_round >= 5
                            || start.elapsed().as_secs_f64() > deadline * dpll_cap
                        {
                            return None;
                        }
                        for s in added {
                            slots.push(s);
                            in_slot.insert(s);
                        }
                        continue 'cegar;
                    }
                };
                if !flipped {
                    slot_val[si] = -slot_val[si];
                    decisions.push((si, true));
                    next_slot = si + 1;
                    for j in next_slot..slots.len() {
                        slot_val[j] = 0;
                    }
                    break;
                }
                slot_val[si] = 0;
            }
        }
    } // 'cegar
}

/// CEGAR over the outer (dep-∅) existentials for ∃∀∃-shaped instances.
/// Repeatedly: pick outer values (via a tiny CDCL over learned blocking
/// clauses), scan rows under those pins, on first UNSAT row extract a
/// minimal pin-core by deletion and block it. All rows SAT → Skolem.
/// Outer-CDCL UNSAT → no constant assignment works → DQBF UNSAT.
#[allow(clippy::too_many_arguments)]
fn outer_cegar(
    cdcl: &mut Cdcl,
    exs: &[Var],
    dep_lists: &[Vec<Var>],
    dep_mask: &[u32],
    outer: &[usize],
    n: usize,
    rows: u32,
    row_assumps: &dyn Fn(u32, &[(Var, i8)]) -> Vec<Lit>,
    row_budget: u64,
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
    unsat_row: &mut Option<u32>,
    unsat_only: bool,
) -> Option<Skolem> {
    let mut model = vec![0i8; n];
    let no = outer.len();
    dbg_ex!(
        debug,
        "outer-CEGAR: {} outer / {} ex, {} rows{}",
        no,
        exs.len(),
        rows,
        if unsat_only { " (UNSAT-only)" } else { "" }
    );
    let mut learned: Vec<Vec<Lit>> = Vec::new();
    // Seed each outer var negative (CDCL default phase); refined per round.
    let mut pins: Vec<(Var, i8)> = outer.iter().map(|&i| (exs[i], -1i8)).collect();
    let mut tables: Vec<Vec<i8>> = (0..exs.len())
        .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
        .collect();
    let mut bad_history: Vec<u32> = Vec::new();
    let mut round = 0u32;
    loop {
        round += 1;
        if start.elapsed().as_secs_f64() > deadline {
            dbg_ex!(debug, "outer-CEGAR: deadline after {} rounds", round);
            return None;
        }
        // Row scan under current pins; stop at first failure. Check
        // previously-bad rows first (likely still bad → O(1) refinement),
        // then sequential. tables only filled on the sequential pass.
        let mut bad: Option<u32> = None;
        for &ub in bad_history.iter().rev().take(32) {
            if !cdcl.solve(&row_assumps(ub, &pins), &mut model, row_budget) && !cdcl.budget_hit {
                bad = Some(ub);
                break;
            }
        }
        if bad.is_none() {
            for (p, &i) in outer.iter().enumerate() {
                tables[i][0] = pins[p].1;
            }
            for ub in 0..rows {
                if ub & 0x3fff == 0 && start.elapsed().as_secs_f64() > deadline {
                    return None;
                }
                let assumps = row_assumps(ub, &pins);
                if !cdcl.solve(&assumps, &mut model, row_budget) {
                    if cdcl.budget_hit {
                        return None;
                    }
                    bad = Some(ub);
                    break;
                }
                if !unsat_only {
                    for (i, &y) in exs.iter().enumerate() {
                        if dep_mask[i] != 0 {
                            let key = extract(ub, dep_mask[i]) as usize;
                            tables[i][key] = if model[y as usize] > 0 { 1 } else { -1 };
                        }
                    }
                }
            }
        }
        let Some(ub) = bad else {
            if unsat_only {
                dbg_ex!(
                    debug,
                    "outer-CEGAR: all rows SAT (UNSAT-only mode, no Skolem)"
                );
                return None;
            }
            dbg_ex!(debug, "outer-CEGAR: SAT after {} rounds", round);
            return Some(build_skolem(exs, dep_lists, &tables));
        };
        if bad_history.last() != Some(&ub) {
            bad_history.push(ub);
        }
        // Minimal pin-core by deletion on row ub.
        let mut core_idx: Vec<usize> = (0..no).collect();
        let mut j = 0;
        while j < core_idx.len() {
            let trial: Vec<(Var, i8)> = core_idx
                .iter()
                .enumerate()
                .filter(|&(k, _)| k != j)
                .map(|(_, &p)| pins[p])
                .collect();
            if !cdcl.solve(&row_assumps(ub, &trial), &mut model, row_budget * 4) && !cdcl.budget_hit
            {
                core_idx.remove(j);
            } else {
                j += 1;
            }
        }
        // Block this core: clause = ∨ ¬pin over core vars (in 1..=no space).
        let block: Vec<Lit> = core_idx
            .iter()
            .map(|&p| {
                let l = (p + 1) as Lit;
                if pins[p].1 > 0 {
                    -l
                } else {
                    l
                }
            })
            .collect();
        dbg_ex!(
            debug,
            "outer-CEGAR r{}: row {} UNSAT, core {}/{}, learned {}",
            round,
            ub,
            core_idx.len(),
            no,
            learned.len() + 1
        );
        if block.is_empty() {
            // Row ub UNSAT under universals alone — already caught by
            // free pass, but guard anyway.
            *unsat_row = Some(ub);
            return None;
        }
        learned.push(block);
        // Re-pick pins satisfying all learned clauses, staying close to
        // the previous round (try previous pins as soft preference, then
        // drop the just-blocked core, then free).
        let mut oc = Cdcl::new(no, &learned);
        let mut om = vec![0i8; no + 1];
        let pref: Vec<Lit> = (0..no)
            .filter(|p| !core_idx.contains(p))
            .map(|p| {
                let l = (p + 1) as Lit;
                if pins[p].1 > 0 {
                    l
                } else {
                    -l
                }
            })
            .collect();
        let ok = oc.solve(&pref, &mut om, 10_000) || oc.solve(&[], &mut om, 10_000);
        if !ok && !oc.budget_hit {
            dbg_ex!(debug, "outer-CEGAR: outer space exhausted → UNSAT");
            *unsat_row = Some(ub);
            return None;
        }
        if !ok {
            return None;
        }
        for (p, &i) in outer.iter().enumerate() {
            pins[p] = (exs[i], if om[p + 1] > 0 { 1 } else { -1 });
        }
    }
}

fn build_skolem(exs: &[Var], dep_lists: &[Vec<Var>], tables: &[Vec<i8>]) -> Skolem {
    let mut sk = Skolem::new();
    for (i, &y) in exs.iter().enumerate() {
        let nd = dep_lists[i].len();
        let size = 1usize << nd;
        let mut bits = vec![0u64; size.div_ceil(64)];
        for j in 0..size {
            if tables[i][j] == 1 {
                bits[j / 64] |= 1u64 << (j % 64);
            }
        }
        sk.insert(y, (bits, nd));
    }
    sk
}

#[inline]
fn extract(ub: u32, mask: u32) -> u32 {
    let mut out = 0u32;
    let mut b = 0;
    let mut m = mask;
    while m != 0 {
        let i = m.trailing_zeros();
        if (ub >> i) & 1 == 1 {
            out |= 1 << b;
        }
        b += 1;
        m &= m - 1;
    }
    out
}
