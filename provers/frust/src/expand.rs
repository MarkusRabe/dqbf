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

pub const MAX_U: usize = 16;

macro_rules! dbg_ex {
    ($d:expr, $($a:tt)*) => { if $d { eprintln!("c [expand] {}", format!($($a)*)); } }
}

pub fn try_expand(
    f: &Formula,
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
    unsat_row: &mut Option<u32>,
) -> Option<Skolem> {
    let nu = f.universals.len();
    if nu > MAX_U {
        dbg_ex!(debug, "skip: |U|={} > MAX_U={}", nu, MAX_U);
        return None;
    }
    let bce = crate::bce::dqbf_bce(f, nu);
    dbg_ex!(
        debug,
        "|U|={} ({} rows), |E|={}, |C|={} (BCE removed {}, ATE removed {})",
        nu,
        1u32 << nu,
        f.deps.len(),
        bce.clauses.len(),
        bce.stack.len(),
        bce.n_ate
    );
    let n = f.n_vars as usize + 1;
    let mut cdcl = Cdcl::new(f.n_vars as usize, &bce.clauses);
    let mut model = vec![0i8; n];
    let exs: Vec<Var> = f.deps.keys().copied().collect();
    let dep_lists: Vec<Vec<Var>> = exs
        .iter()
        .map(|y| f.deps[y].iter().copied().collect())
        .collect();
    let u_idx: HashMap<Var, usize> = f
        .universals
        .iter()
        .enumerate()
        .map(|(i, &u)| (u, i))
        .collect();
    let dep_mask: Vec<u32> = dep_lists
        .iter()
        .map(|ds| ds.iter().map(|d| 1u32 << u_idx[d]).sum())
        .collect();
    let rows = 1u32 << nu;
    let row_budget: u64 = ((1_000_000 / rows.max(1)) as u64).max(100);
    let row_assumps = |f: &Formula, ub: u32, extra: &[(Var, i8)]| -> Vec<Lit> {
        let mut a: Vec<Lit> = f
            .universals
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
        let assumps = row_assumps(f, ub, &[]);
        if !cdcl.solve(&assumps, &mut model, row_budget) {
            dbg_ex!(debug, "free pass row {}: UNSAT/budget", ub);
            if !cdcl.budget_hit {
                *unsat_row = Some(ub);
            }
            return None;
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
    if slots.is_empty() {
        // No conflicts: the free pass IS a consistent Skolem.
        let mut sk = build_skolem(&exs, &dep_lists, &first_seen);
        crate::bce::reconstruct(&mut sk, f, &bce.stack);
        return Some(sk);
    }
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
            if iters & 0x3f == 0 && start.elapsed().as_secs_f64() > deadline * 0.7 {
                return None;
            }
            // Decide one slot at a time so CDCL-UNSAT can prune subtrees.
            if next_slot < slots.len() {
                let (i, k) = slots[next_slot];
                slot_val[next_slot] = first_seen[i][k]; // prefer first-seen value
                decisions.push((next_slot, false));
                next_slot += 1;
            }
            let all_decided = next_slot >= slots.len();
            // Run all rows with current slot assignment + greedy fill.
            let mut tables: Vec<Vec<i8>> = (0..exs.len())
                .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
                .collect();
            for (p, &(i, k)) in slots.iter().enumerate() {
                tables[i][k] = slot_val[p];
            }
            let mut prune = false; // CDCL-UNSAT under slot pins → backtrack
            let mut soft_conflict = false; // greedy-fill disagree → decide more
            for ub in 0..rows {
                let pins: Vec<(Var, i8)> = row_slots[ub as usize]
                    .iter()
                    .filter(|&&p| slot_val[p] != 0)
                    .map(|&p| (exs[slots[p].0], slot_val[p]))
                    .collect();
                cdcl.reset_phase();
                let assumps = row_assumps(f, ub, &pins);
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
                let mut sk = build_skolem(&exs, &dep_lists, &tables);
                crate::bce::reconstruct(&mut sk, f, &bce.stack);
                return Some(sk);
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
                            || start.elapsed().as_secs_f64() > deadline * 0.7
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
