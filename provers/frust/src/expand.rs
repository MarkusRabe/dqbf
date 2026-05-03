//! Universal expansion + per-row DPLL for small |U|.
//!
//! For each of the 2^|U| universal assignments, substitute and SAT-solve
//! the resulting propositional formula. An existential y with deps D may
//! take a different value per assignment, but assignments that agree on
//! D must give y the same value — enforced by fixing y from earlier rows
//! that share its D-projection.

use crate::aiger::Skolem;
use crate::formula::{var, Clause, Formula, Var};
use std::collections::HashMap;

pub const MAX_U: usize = 16;

/// Greedy expansion. Returns Some(sk) only when it finds a verifiable
/// Skolem model; otherwise None (caller falls back to saturation).
/// Never concludes UNSAT — that requires a checkable proof.
pub fn try_expand(f: &Formula) -> Option<Skolem> {
    let nu = f.universals.len();
    if nu > MAX_U {
        return None;
    }
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
    // For each existential, the bitmask of universal indices it depends on.
    let dep_mask: Vec<u32> = dep_lists
        .iter()
        .map(|ds| ds.iter().map(|d| 1u32 << u_idx[d]).sum())
        .collect();
    // table[i]: dep-projection -> chosen value for existential i.
    let mut tables: Vec<HashMap<u32, bool>> = vec![HashMap::new(); exs.len()];

    let n = f.n_vars as usize + 1;
    let mut polarity = vec![0i8; n]; // 0=unset, 1=true, -1=false

    for ub in 0..(1u32 << nu) {
        // Reset polarity, set universals from ub.
        for p in polarity.iter_mut() {
            *p = 0;
        }
        for (i, &u) in f.universals.iter().enumerate() {
            polarity[u as usize] = if (ub >> i) & 1 == 1 { 1 } else { -1 };
        }
        // Pin existentials whose dep-projection has been decided by an earlier row.
        for (i, &y) in exs.iter().enumerate() {
            let key = ub & dep_mask[i];
            if let Some(&v) = tables[i].get(&key) {
                polarity[y as usize] = if v { 1 } else { -1 };
            }
        }
        // DPLL on the remaining vars.
        if !dpll(&f.clauses, &mut polarity) {
            return None;
        }
        for (i, &y) in exs.iter().enumerate() {
            let key = ub & dep_mask[i];
            tables[i].entry(key).or_insert(polarity[y as usize] == 1);
        }
    }
    // Build Skolem bitmaps.
    let mut sk = Skolem::new();
    for (i, &y) in exs.iter().enumerate() {
        let ndeps = dep_lists[i].len();
        let size = 1usize << ndeps;
        let mut bits = vec![0u64; (size + 63) / 64];
        for kb in 0..size as u32 {
            let mut key = 0u32;
            for (b, d) in dep_lists[i].iter().enumerate() {
                if (kb >> b) & 1 == 1 {
                    key |= 1u32 << u_idx[d];
                }
            }
            if tables[i].get(&key).copied().unwrap_or(false) {
                bits[kb as usize / 64] |= 1u64 << (kb % 64);
            }
        }
        sk.insert(y, (bits, ndeps));
    }
    Some(sk)
}

/// Iterative DPLL with a trail (no per-branch clone).
fn dpll(clauses: &[Clause], pol: &mut [i8]) -> bool {
    let mut trail: Vec<usize> = Vec::new();
    let mut decisions: Vec<(usize, usize, bool)> = Vec::new(); // (var, trail-len before, tried_neg)
    loop {
        if !unit_propagate(clauses, pol, &mut trail) {
            loop {
                let (dv, tl, tried_neg) = match decisions.pop() {
                    Some(d) => d,
                    None => return false,
                };
                while trail.len() > tl {
                    pol[trail.pop().unwrap()] = 0;
                }
                if !tried_neg {
                    pol[dv] = -1;
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
                decisions.push((v, trail.len(), false));
                pol[v] = 1;
                trail.push(v);
            }
        }
    }
}

fn unit_propagate(clauses: &[Clause], pol: &mut [i8], trail: &mut Vec<usize>) -> bool {
    loop {
        let mut changed = false;
        for c in clauses {
            let mut unassigned: Option<i32> = None;
            let mut sat = false;
            let mut multi = false;
            for &l in c {
                let v = var(l) as usize;
                let p = pol[v];
                if p != 0 {
                    if (l > 0) == (p > 0) {
                        sat = true;
                        break;
                    }
                } else if unassigned.is_some() {
                    multi = true;
                } else {
                    unassigned = Some(l);
                }
            }
            if sat {
                continue;
            }
            match (unassigned, multi) {
                (None, _) => return false,
                (Some(l), false) => {
                    let v = var(l) as usize;
                    pol[v] = if l > 0 { 1 } else { -1 };
                    trail.push(v);
                    changed = true;
                }
                _ => {}
            }
        }
        if !changed {
            return true;
        }
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
