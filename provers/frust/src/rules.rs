//! Fork-resolution inference rules.

use crate::formula::{var, Clause, Formula, Lit, Var};
use std::collections::BTreeSet;

pub fn is_tautology(c: &Clause) -> bool {
    c.iter().any(|&l| l > 0 && c.contains(&(-l)))
}

pub fn resolve(c1: &Clause, c2: &Clause, pivot: Var) -> Option<Clause> {
    let p = pivot as Lit;
    let (pos, neg) = if c1.contains(&p) && c2.contains(&(-p)) {
        (c1, c2)
    } else if c1.contains(&(-p)) && c2.contains(&p) {
        (c2, c1)
    } else {
        return None;
    };
    let mut r: Clause = pos.iter().copied().filter(|&l| l != p).collect();
    for &l in neg {
        if l == -p {
            continue;
        }
        if r.contains(&(-l)) {
            return None; // tautology
        }
        r.insert(l);
    }
    Some(r)
}

pub fn universal_reduce(f: &Formula, c: &Clause) -> Clause {
    let mut cur = c.clone();
    loop {
        let mut ex_deps: BTreeSet<Var> = BTreeSet::new();
        for &l in &cur {
            let v = var(l);
            if f.is_existential(v) {
                if let Some(d) = f.deps.get(&v) {
                    ex_deps.extend(d);
                }
            }
        }
        let mut dropped = false;
        let to_drop: Vec<Lit> = cur
            .iter()
            .copied()
            .filter(|&l| {
                let v = var(l);
                f.is_universal(v) && !ex_deps.contains(&v) && !cur.contains(&(-l))
            })
            .collect();
        for l in to_drop {
            cur.remove(&l);
            dropped = true;
        }
        if !dropped {
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
    let c1: Clause = part.clone();
    let c2: Clause = c.difference(part).copied().collect();
    let d1 = f.clause_dep(&c1);
    let d2 = f.clause_dep(&c2);
    let x = f.n_vars + 1;
    f.add_existential(x, d1.intersection(&d2).copied().collect());
    let mut left = c1;
    left.insert(x as Lit);
    let mut right = c2;
    right.insert(-(x as Lit));
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
