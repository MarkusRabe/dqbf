//! Universal expansion + per-row DPLL for small |U|.
//!
//! Two-pass: a free pass solves every row unconstrained, recording (a)
//! which existentials were ever DECIDED (vs unit-propagated) — those are
//! the only ones that need cross-row consistency — and (b) per-key vote
//! tallies. The pinned pass seeds the *constrained* partial-dep
//! existentials from the votes and re-solves; defined / full-dep vars
//! are left to unit-prop. Only emits SAT (cert is checkable).

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
) -> Option<Skolem> {
    let nu = f.universals.len();
    if nu > MAX_U {
        dbg_ex!(debug, "skip: |U|={} > MAX_U={}", nu, MAX_U);
        return None;
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

    // ---- Free pass --------------------------------------------------
    // votes[i][k] tallies polarity; first_seen[i][k] holds the first
    // value; conflict[i] marks existentials whose free-pass value
    // differed across rows with the same dep-key.
    let mut votes: Vec<Vec<i32>> = (0..exs.len())
        .map(|i| vec![0i32; 1usize << dep_lists[i].len()])
        .collect();
    let mut first_seen: Vec<Vec<i8>> = (0..exs.len())
        .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
        .collect();
    let mut key_conflict: Vec<Vec<bool>> = (0..exs.len())
        .map(|i| vec![false; 1usize << dep_lists[i].len()])
        .collect();
    let mut conflict = vec![false; exs.len()];
    for ub in 0..rows {
        if start.elapsed().as_secs_f64() > deadline * 0.4 {
            return None;
        }
        cdcl.reset_phase();
        let assumps = row_assumps(f, ub, &[]);
        if !cdcl.solve(&assumps, &mut model, row_budget) {
            dbg_ex!(
                debug,
                "free pass row {}: UNSAT/budget — falling through",
                ub
            );
            return None;
        }
        for (i, &y) in exs.iter().enumerate() {
            let key = extract(ub, dep_mask[i]) as usize;
            let v: i8 = if model[y as usize] > 0 { 1 } else { -1 };
            votes[i][key] += v as i32;
            if first_seen[i][key] == 0 {
                first_seen[i][key] = v;
            } else if first_seen[i][key] != v {
                conflict[i] = true;
                key_conflict[i][key] = true;
            }
        }
    }
    // If no conflicts at all, the free pass IS a valid Skolem.
    // constrained = vars with a conflict (regardless of dep width — a
    // full-dep var has one row per key so never conflicts).
    let constrained = conflict;
    let n_constrained = constrained.iter().filter(|&&c| c).count();
    let n_slots: usize = key_conflict
        .iter()
        .map(|kc| kc.iter().filter(|&&c| c).count())
        .sum();
    dbg_ex!(
        debug,
        "free pass done in {:.2}s; {} constrained vars, {} conflicting slots, row_budget={}",
        start.elapsed().as_secs_f64(),
        n_constrained,
        n_slots,
        row_budget
    );

    // ---- Pinned passes (4 polarity strategies) ----------------------
    for &(first, use_votes) in &[(1i8, true), (-1, true), (1, false), (-1, false)] {
        if start.elapsed().as_secs_f64() > deadline * 0.6 {
            return None;
        }
        let mut tables: Vec<Vec<i8>> = (0..exs.len())
            .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
            .collect();
        if use_votes {
            for (i, t) in tables.iter_mut().enumerate() {
                if !constrained[i] {
                    continue;
                }
                for (k, slot) in t.iter_mut().enumerate() {
                    *slot = match votes[i][k].signum() {
                        1 => 1,
                        -1 => -1,
                        _ => 0,
                    };
                }
            }
        }
        let _ = first;
        let mut ok = true;
        let mut row_conflict = vec![false; exs.len()];
        for ub in 0..rows {
            let pins: Vec<(Var, i8)> = exs
                .iter()
                .enumerate()
                .map(|(i, &y)| (y, tables[i][extract(ub, dep_mask[i]) as usize]))
                .filter(|&(_, t)| t != 0)
                .collect();
            let assumps = row_assumps(f, ub, &pins);
            if !cdcl.solve(&assumps, &mut model, row_budget) {
                ok = false;
                break;
            }
            for (i, &y) in exs.iter().enumerate() {
                let key = extract(ub, dep_mask[i]) as usize;
                let v: i8 = if model[y as usize] > 0 { 1 } else { -1 };
                if tables[i][key] == 0 {
                    tables[i][key] = v;
                } else if tables[i][key] != v {
                    row_conflict[i] = true;
                }
            }
        }
        if !ok || row_conflict.iter().any(|&c| c) {
            dbg_ex!(
                debug,
                "heuristic (first={}, votes={}): {} ({} new conflicts)",
                first,
                use_votes,
                if !ok { "row UNSAT" } else { "row_conflict" },
                row_conflict.iter().filter(|&&c| c).count()
            );
            continue;
        }
        dbg_ex!(
            debug,
            "heuristic (first={}, votes={}): SAT",
            first,
            use_votes
        );
        return Some(build_skolem(&exs, &dep_lists, &tables));
    }

    // ---- Enumeration fallback (iDQ-style) ---------------------------
    // Slot list: only the (i, k) pairs that actually disagreed.
    let mut slots: Vec<(usize, usize)> = Vec::new();
    for (i, kc) in key_conflict.iter().enumerate() {
        for (k, &c) in kc.iter().enumerate() {
            if c {
                slots.push((i, k));
            }
        }
    }
    if slots.is_empty() {
        dbg_ex!(debug, "no slots — falling through");
        return None; // no slots but heuristics failed → not expand-SAT
    }
    let mut in_slots: std::collections::HashSet<(usize, usize)> = slots.iter().copied().collect();
    let mut cegar_round = 0;
    'cegar: loop {
        cegar_round += 1;
        dbg_ex!(
            debug,
            "slot-DPLL round {} on {} slots",
            cegar_round,
            slots.len()
        );
        // ---- Slot-level DPLL (CEGAR-ish) -------------------------------
        // Order slots by |vote| descending — most-determined first.
        slots.sort_by_key(|&(i, k)| -(votes[i][k].abs()));
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
        // Cache: last (slot_val signature, model) per row.
        let mut row_cache: Vec<Option<(u64, Vec<i8>)>> = vec![None; rows as usize];
        let row_sig = |slot_val: &[i8], rs: &[usize]| -> u64 {
            let mut h = 0u64;
            for &p in rs {
                h = h.wrapping_mul(3).wrapping_add(slot_val[p] as u64);
            }
            h
        };
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
                let pref = if votes[i][k] >= 0 { 1i8 } else { -1 };
                slot_val[next_slot] = pref;
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
                let rs = &row_slots[ub as usize];
                let sig = row_sig(&slot_val, rs);
                let cached: Vec<i8> = if let Some((csig, m)) = &row_cache[ub as usize] {
                    if *csig == sig {
                        m.clone()
                    } else {
                        Vec::new()
                    }
                } else {
                    Vec::new()
                };
                let row_model = if cached.is_empty() {
                    let pins: Vec<(Var, i8)> = rs
                        .iter()
                        .filter(|&&p| slot_val[p] != 0)
                        .map(|&p| {
                            let (i, _k) = slots[p];
                            (exs[i], slot_val[p])
                        })
                        .collect();
                    cdcl.reset_phase();
                    let assumps = row_assumps(f, ub, &pins);
                    if !cdcl.solve(&assumps, &mut model, row_budget) {
                        prune = true;
                        break;
                    }
                    row_cache[ub as usize] = Some((sig, model.clone()));
                    model.clone()
                } else {
                    cached
                };
                for (i, &y) in exs.iter().enumerate() {
                    let key = extract(ub, dep_mask[i]) as usize;
                    let v: i8 = if row_model[y as usize] > 0 { 1 } else { -1 };
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
                            .filter(|s| !in_slots.contains(s))
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
                            in_slots.insert(s);
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
        let mut bits = vec![0u64; (size + 63) / 64];
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
