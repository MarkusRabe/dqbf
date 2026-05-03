//! Fork-resolution inference rules over sorted Vec<i32> clauses.

use crate::formula::{var, Clause, Formula, Lit, Var};
use std::collections::BTreeSet;

pub fn is_tautology(c: &Clause) -> bool {
    // Sorted: a tautology has l and -l adjacent only if both signs of same var.
    // Simpler: linear scan with a small set is fine for short clauses.
    for &l in c {
        if l > 0 && c.binary_search(&(-l)).is_ok() {
            return true;
        }
    }
    false
}

/// Sorted-merge resolution. Returns None if pivot polarities not present
/// or the resolvent would be a tautology.
pub fn resolve(c1: &Clause, c2: &Clause, pivot: Var) -> Option<Clause> {
    let p = pivot as Lit;
    let (pos, neg) = if c1.binary_search(&p).is_ok() && c2.binary_search(&(-p)).is_ok() {
        (c1, c2)
    } else if c1.binary_search(&(-p)).is_ok() && c2.binary_search(&p).is_ok() {
        (c2, c1)
    } else {
        return None;
    };
    let mut out = Vec::with_capacity(pos.len() + neg.len() - 2);
    let (mut i, mut j) = (0usize, 0usize);
    loop {
        let a = if i < pos.len() { Some(pos[i]) } else { None };
        let b = if j < neg.len() { Some(neg[j]) } else { None };
        let l = match (a, b) {
            (None, None) => break,
            (Some(x), None) => {
                i += 1;
                x
            }
            (None, Some(y)) => {
                j += 1;
                y
            }
            (Some(x), Some(y)) => {
                if x < y {
                    i += 1;
                    x
                } else if y < x {
                    j += 1;
                    y
                } else {
                    i += 1;
                    j += 1;
                    x
                }
            }
        };
        if l == p || l == -p {
            continue;
        }
        if let Some(&last) = out.last() {
            if last == -l {
                return None; // tautology (l and -l would be adjacent in sorted order)
            }
        }
        out.push(l);
    }
    // tautology check: -l ... l can be non-adjacent in i32 sort (e.g., -3, -1, 1, 3)
    // but actually -l < 0 < l, and any other lit between has different abs.
    // Safer: full check.
    if is_tautology(&out) {
        return None;
    }
    Some(out)
}

pub fn universal_reduce(f: &Formula, c: &Clause) -> Clause {
    let mut cur = c.to_vec();
    loop {
        let mut ex_deps: BTreeSet<Var> = BTreeSet::new();
        for &l in &cur {
            let v = var(l);
            if let Some(d) = f.deps.get(&v) {
                ex_deps.extend(d);
            }
        }
        let before = cur.len();
        cur.retain(|&l| {
            let v = var(l);
            !(f.is_universal(v) && !ex_deps.contains(&v))
        });
        if cur.len() == before {
            return cur;
        }
    }
}

pub struct ForkResult {
    pub fresh: Var,
    pub left: Clause,
    pub right: Clause,
}

pub fn fork_extend(f: &mut Formula, c: &Clause, part: &Clause) -> ForkResult {
    let part_set: BTreeSet<Lit> = part.iter().copied().collect();
    let c1 = part.clone();
    let c2: Clause = c
        .iter()
        .copied()
        .filter(|l| !part_set.contains(l))
        .collect();
    let d1 = f.clause_dep(&c1);
    let d2 = f.clause_dep(&c2);
    let x = f.n_vars + 1;
    f.add_existential(x, d1.intersection(&d2).copied().collect());
    let mut left = c1;
    left.push(x as Lit);
    left.sort_unstable();
    let mut right = c2;
    right.push(-(x as Lit));
    right.sort_unstable();
    ForkResult {
        fresh: x,
        left,
        right,
    }
}

pub fn find_information_fork(f: &Formula, c: &Clause) -> Option<(Var, Var)> {
    let exs: Vec<Var> = c
        .iter()
        .map(|&l| var(l))
        .filter(|&v| f.is_existential(v))
        .collect();
    for i in 0..exs.len() {
        for j in (i + 1)..exs.len() {
            let (a, b) = (exs[i], exs[j]);
            let da = &f.deps[&a];
            let db = &f.deps[&b];
            if !da.is_subset(db) && !db.is_subset(da) {
                return Some((a, b));
            }
        }
    }
    None
}
