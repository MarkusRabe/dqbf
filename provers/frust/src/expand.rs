//! Universal expansion + per-row DPLL for small |U|.
//!
//! For each of the 2^|U| universal assignments, substitute and SAT-solve
//! the resulting propositional formula. An existential y with deps D may
//! take a different value per assignment, but assignments that agree on
//! D must give y the same value — enforced by fixing y from earlier rows
//! that share its D-projection.

use crate::aiger::Skolem;
use crate::formula::{var, Clause, Formula, Var};
use std::collections::{BTreeMap, HashMap};

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
        let model = match dpll(&f.clauses, polarity.clone()) {
            Some(m) => m,
            None => return None, // greedy failed; fall back to saturation
        };
        // Record the existential choices for this row's dep-projections.
        for (i, &y) in exs.iter().enumerate() {
            let key = ub & dep_mask[i];
            tables[i].entry(key).or_insert(model[y as usize] == 1);
        }
    }
    // Build Skolem from tables.
    let mut sk = Skolem::new();
    for (i, &y) in exs.iter().enumerate() {
        let mut tbl = BTreeMap::new();
        let ndeps = dep_lists[i].len();
        for kb in 0..(1u32 << ndeps) {
            // map kb (over dep_lists[i]) to ub-mask
            let mut key = 0u32;
            for (b, d) in dep_lists[i].iter().enumerate() {
                if (kb >> b) & 1 == 1 {
                    key |= 1u32 << u_idx[d];
                }
            }
            let v = tables[i].get(&key).copied().unwrap_or(false);
            let kvec: Vec<bool> = (0..ndeps).map(|b| (kb >> b) & 1 == 1).collect();
            tbl.insert(kvec, v);
        }
        sk.insert(y, tbl);
    }
    Some(sk)
}

/// Tiny DPLL: unit prop + first-unset branch. Returns a total model or None.
fn dpll(clauses: &[Clause], mut pol: Vec<i8>) -> Option<Vec<i8>> {
    if !unit_propagate(clauses, &mut pol) {
        return None;
    }
    // Find an unset var that appears in some unsatisfied clause.
    let pick = pick_var(clauses, &pol);
    let pick = match pick {
        Some(v) => v,
        None => return Some(pol), // all clauses satisfied
    };
    for &val in &[1i8, -1i8] {
        let mut p2 = pol.clone();
        p2[pick] = val;
        if let Some(m) = dpll(clauses, p2) {
            return Some(m);
        }
    }
    None
}

fn unit_propagate(clauses: &[Clause], pol: &mut Vec<i8>) -> bool {
    loop {
        let mut changed = false;
        for c in clauses {
            let mut unassigned: Option<i32> = None;
            let mut sat = false;
            let mut multi = false;
            for &l in c {
                let v = var(l) as usize;
                match (pol[v], l > 0) {
                    (1, true) | (-1, false) => {
                        sat = true;
                        break;
                    }
                    (0, _) => {
                        if unassigned.is_some() {
                            multi = true;
                        } else {
                            unassigned = Some(l);
                        }
                    }
                    _ => {}
                }
            }
            if sat {
                continue;
            }
            match (unassigned, multi) {
                (None, _) => return false, // conflict
                (Some(l), false) => {
                    pol[var(l) as usize] = if l > 0 { 1 } else { -1 };
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
            match (pol[v], l > 0) {
                (1, true) | (-1, false) => {
                    sat = true;
                    break;
                }
                (0, _) => cand = Some(v),
                _ => {}
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
