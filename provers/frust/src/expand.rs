//! Universal expansion + per-row DPLL for small |U|.
//!
//! Two-pass: a free pass solves every row unconstrained, recording (a)
//! which existentials were ever DECIDED (vs unit-propagated) — those are
//! the only ones that need cross-row consistency — and (b) per-key vote
//! tallies. The pinned pass seeds the *constrained* partial-dep
//! existentials from the votes and re-solves; defined / full-dep vars
//! are left to unit-prop. Only emits SAT (cert is checkable).

use crate::aiger::Skolem;
use crate::formula::{var, Clause, Formula, Var};
use std::collections::HashMap;

pub const MAX_U: usize = 16;

pub fn try_expand(f: &Formula, deadline: f64, start: &std::time::Instant) -> Option<Skolem> {
    let nu = f.universals.len();
    if nu > MAX_U {
        return None;
    }
    let n = f.n_vars as usize + 1;
    let occ = build_occ(&f.clauses, n);
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
    let row_budget: u32 = (200_000 / rows.max(1)).max(50);

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
    let mut polarity = vec![0i8; n];
    for ub in 0..rows {
        if start.elapsed().as_secs_f64() > deadline * 0.4 {
            return None;
        }
        reset_row(f, &mut polarity, ub);
        let mut decided: Vec<usize> = Vec::new();
        if !dpll(&f.clauses, &occ, &mut polarity, 1, &mut decided, row_budget) {
            return None;
        }
        for (i, &y) in exs.iter().enumerate() {
            let key = extract(ub, dep_mask[i]) as usize;
            let v: i8 = if polarity[y as usize] > 0 { 1 } else { -1 };
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
        let mut ok = true;
        let mut row_conflict = vec![false; exs.len()];
        for ub in 0..rows {
            reset_row(f, &mut polarity, ub);
            for (i, &y) in exs.iter().enumerate() {
                let key = extract(ub, dep_mask[i]) as usize;
                let t = tables[i][key];
                if t != 0 {
                    polarity[y as usize] = t;
                }
            }
            let mut decided: Vec<usize> = Vec::new();
            if !dpll(
                &f.clauses,
                &occ,
                &mut polarity,
                first,
                &mut decided,
                row_budget,
            ) {
                ok = false;
                break;
            }
            for (i, &y) in exs.iter().enumerate() {
                let key = extract(ub, dep_mask[i]) as usize;
                let v: i8 = if polarity[y as usize] > 0 { 1 } else { -1 };
                if tables[i][key] == 0 {
                    tables[i][key] = v;
                } else if tables[i][key] != v {
                    row_conflict[i] = true;
                }
            }
        }
        if !ok || row_conflict.iter().any(|&c| c) {
            continue;
        }
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
        return None; // no slots but heuristics failed → not expand-SAT
    }
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
    loop {
        iters += 1;
        if iters & 0x3f == 0 && start.elapsed().as_secs_f64() > deadline * 0.7 {
            return None;
        }
        // Decide next unset slot, prefer vote sign.
        if next_slot < slots.len() {
            let (i, k) = slots[next_slot];
            let pref = if votes[i][k] >= 0 { 1i8 } else { -1 };
            slot_val[next_slot] = pref;
            decisions.push((next_slot, false));
            next_slot += 1;
        }
        // Run all rows with current slot assignment + greedy fill.
        let mut tables: Vec<Vec<i8>> = (0..exs.len())
            .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
            .collect();
        for (p, &(i, k)) in slots.iter().enumerate() {
            tables[i][k] = slot_val[p];
        }
        let mut fail = false;
        for ub in 0..rows {
            let rs = &row_slots[ub as usize];
            let sig = row_sig(&slot_val, rs);
            let model: Vec<i8> = if let Some((csig, m)) = &row_cache[ub as usize] {
                if *csig == sig {
                    m.clone()
                } else {
                    Vec::new()
                }
            } else {
                Vec::new()
            };
            let model = if model.is_empty() {
                reset_row(f, &mut polarity, ub);
                for (i, &y) in exs.iter().enumerate() {
                    let key = extract(ub, dep_mask[i]) as usize;
                    let t = tables[i][key];
                    if t != 0 {
                        polarity[y as usize] = t;
                    }
                }
                let mut decided: Vec<usize> = Vec::new();
                if !dpll(&f.clauses, &occ, &mut polarity, 1, &mut decided, row_budget) {
                    fail = true;
                    break;
                }
                row_cache[ub as usize] = Some((sig, polarity.clone()));
                polarity.clone()
            } else {
                model
            };
            for (i, &y) in exs.iter().enumerate() {
                let key = extract(ub, dep_mask[i]) as usize;
                let v: i8 = if model[y as usize] > 0 { 1 } else { -1 };
                if tables[i][key] == 0 {
                    tables[i][key] = v;
                } else if tables[i][key] != v {
                    fail = true;
                }
            }
            if fail {
                break;
            }
        }
        if !fail {
            return Some(build_skolem(&exs, &dep_lists, &tables));
        }
        // Backtrack.
        loop {
            let (si, flipped) = match decisions.pop() {
                Some(d) => d,
                None => return None,
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
fn reset_row(f: &Formula, pol: &mut [i8], ub: u32) {
    for p in pol.iter_mut() {
        *p = 0;
    }
    for (i, &u) in f.universals.iter().enumerate() {
        pol[u as usize] = if (ub >> i) & 1 == 1 { 1 } else { -1 };
    }
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

fn build_occ(clauses: &[Clause], n: usize) -> Vec<Vec<u32>> {
    let mut occ = vec![Vec::new(); 2 * n];
    for (ci, c) in clauses.iter().enumerate() {
        for &l in c {
            let idx = 2 * var(l) as usize + if l < 0 { 1 } else { 0 };
            occ[idx].push(ci as u32);
        }
    }
    occ
}

fn dpll(
    clauses: &[Clause],
    occ: &[Vec<u32>],
    pol: &mut [i8],
    first: i8,
    decided: &mut Vec<usize>,
    max_conflicts: u32,
) -> bool {
    let mut trail: Vec<usize> = Vec::new();
    let mut decisions: Vec<(usize, usize, bool)> = Vec::new();
    let mut prop_from = 0usize;
    let mut conflicts = 0u32;
    if !scan_all(clauses, pol, &mut trail) {
        return false;
    }
    loop {
        if conflicts > max_conflicts {
            return false;
        }
        if !propagate(clauses, occ, pol, &mut trail, &mut prop_from) {
            conflicts += 1;
            loop {
                let (dv, tl, flipped) = match decisions.pop() {
                    Some(d) => d,
                    None => return false,
                };
                while trail.len() > tl {
                    pol[trail.pop().unwrap()] = 0;
                }
                prop_from = trail.len();
                if !flipped {
                    pol[dv] = -first;
                    trail.push(dv);
                    decisions.push((dv, tl, true));
                    break;
                }
            }
            continue;
        }
        match pick_var(clauses, pol) {
            None => return true,
            Some(v) => {
                decided.push(v);
                decisions.push((v, trail.len(), false));
                pol[v] = first;
                trail.push(v);
            }
        }
    }
}

fn scan_all(clauses: &[Clause], pol: &mut [i8], trail: &mut Vec<usize>) -> bool {
    loop {
        let mut changed = false;
        for c in clauses {
            match clause_status(c, pol) {
                Status::Conflict => return false,
                Status::Unit(l) => {
                    let v = var(l) as usize;
                    if pol[v] == 0 {
                        pol[v] = if l > 0 { 1 } else { -1 };
                        trail.push(v);
                        changed = true;
                    }
                }
                _ => {}
            }
        }
        if !changed {
            return true;
        }
    }
}

fn propagate(
    clauses: &[Clause],
    occ: &[Vec<u32>],
    pol: &mut [i8],
    trail: &mut Vec<usize>,
    from: &mut usize,
) -> bool {
    while *from < trail.len() {
        let v = trail[*from];
        *from += 1;
        let p = pol[v];
        let neg_idx = 2 * v + if p > 0 { 1 } else { 0 };
        for &ci in &occ[neg_idx] {
            match clause_status(&clauses[ci as usize], pol) {
                Status::Conflict => return false,
                Status::Unit(l) => {
                    let u = var(l) as usize;
                    if pol[u] == 0 {
                        pol[u] = if l > 0 { 1 } else { -1 };
                        trail.push(u);
                    }
                }
                _ => {}
            }
        }
    }
    true
}

enum Status {
    Sat,
    Conflict,
    Unit(i32),
    Unresolved,
}

#[inline]
fn clause_status(c: &Clause, pol: &[i8]) -> Status {
    let mut unassigned: Option<i32> = None;
    let mut multi = false;
    for &l in c {
        let p = pol[var(l) as usize];
        if p != 0 {
            if (l > 0) == (p > 0) {
                return Status::Sat;
            }
        } else if unassigned.is_some() {
            multi = true;
        } else {
            unassigned = Some(l);
        }
    }
    match (unassigned, multi) {
        (None, _) => Status::Conflict,
        (Some(l), false) => Status::Unit(l),
        _ => Status::Unresolved,
    }
}

fn pick_var(clauses: &[Clause], pol: &[i8]) -> Option<usize> {
    for c in clauses {
        let mut sat = false;
        let mut cand = None;
        for &l in c {
            let v = var(l) as usize;
            let p = pol[v];
            if p != 0 {
                if (l > 0) == (p > 0) {
                    sat = true;
                    break;
                }
            } else {
                cand = Some(v);
            }
        }
        if !sat {
            if let Some(v) = cand {
                return Some(v);
            }
        }
    }
    None
}
