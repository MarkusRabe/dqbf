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
    let dep_mask: Vec<u32> = dep_lists
        .iter()
        .map(|ds| ds.iter().map(|d| 1u32 << u_idx[d]).sum())
        .collect();
    // tables[i][key] = 0 unset / 1 true / -1 false
    let mut tables: Vec<Vec<i8>> = (0..exs.len())
        .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
        .collect();
    // Compact dep-key: pext-style extract of ub bits at dep positions.
    let extract = |ub: u32, mask: u32| -> u32 {
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
    };

    let n = f.n_vars as usize + 1;
    let mut polarity = vec![0i8; n];
    let occ = build_occ(&f.clauses, n);

    for ub in 0..(1u32 << nu) {
        for p in polarity.iter_mut() {
            *p = 0;
        }
        for (i, &u) in f.universals.iter().enumerate() {
            polarity[u as usize] = if (ub >> i) & 1 == 1 { 1 } else { -1 };
        }
        for (i, &y) in exs.iter().enumerate() {
            let key = extract(ub, dep_mask[i]) as usize;
            let t = tables[i][key];
            if t != 0 {
                polarity[y as usize] = t;
            }
        }
        if !dpll(&f.clauses, &occ, &mut polarity) {
            return None;
        }
        for (i, &y) in exs.iter().enumerate() {
            let key = extract(ub, dep_mask[i]) as usize;
            if tables[i][key] == 0 {
                tables[i][key] = polarity[y as usize].max(-1).min(1);
                if tables[i][key] == 0 {
                    tables[i][key] = -1;
                }
            }
        }
    }
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
    Some(sk)
}

/// occ[2*v] = clause indices containing +v; occ[2*v+1] = containing -v.
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

fn dpll(clauses: &[Clause], occ: &[Vec<u32>], pol: &mut [i8]) -> bool {
    let mut trail: Vec<usize> = Vec::new();
    let mut decisions: Vec<(usize, usize, bool)> = Vec::new();
    let mut prop_from = 0usize;
    // Seed: enqueue all initially-set vars by pretending a "full scan" once.
    if !scan_all(clauses, pol, &mut trail) {
        return false;
    }
    loop {
        if !propagate(clauses, occ, pol, &mut trail, &mut prop_from) {
            loop {
                let (dv, tl, tried_neg) = match decisions.pop() {
                    Some(d) => d,
                    None => return false,
                };
                while trail.len() > tl {
                    pol[trail.pop().unwrap()] = 0;
                }
                prop_from = trail.len();
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

/// One initial linear scan (handles units present in input under fixed pol).
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

/// Occurrence-driven propagation: only re-check clauses containing the
/// negation of newly-assigned literals.
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
