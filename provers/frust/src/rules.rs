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
    if f.universals.len() > 64 {
        return universal_reduce_set(f, c);
    }
    let mut ex_mask = 0u64;
    for &l in c {
        let v = var(l);
        if f.is_existential(v) {
            ex_mask |= f.dep_mask(v);
        }
    }
    let out: Clause = c
        .iter()
        .copied()
        .filter(|&l| {
            let v = var(l);
            !f.is_universal(v) || (f.dep_mask(v) & ex_mask) != 0
        })
        .collect();
    if out.len() != c.len() {
        return universal_reduce(f, &out);
    }
    out
}

fn universal_reduce_set(f: &Formula, c: &Clause) -> Clause {
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

/// FEx on clause `c`, partitioning by the first information-fork pair.
pub fn choose_fork(f: &mut Formula, c: &Clause) -> Option<(Clause, ForkResult)> {
    let (a, _b) = find_information_fork(f, c)?;
    let da = f.deps[&a].clone();
    let part: Clause = c
        .iter()
        .copied()
        .filter(|&l| var(l) == a || f.dep(var(l)).is_subset(&da))
        .collect();
    let part_set: BTreeSet<Lit> = part.iter().copied().collect();
    let c2: Clause = c
        .iter()
        .copied()
        .filter(|l| !part_set.contains(l))
        .collect();
    let d1 = f.clause_dep(&part);
    let d2 = f.clause_dep(&c2);
    let inter: BTreeSet<Var> = d1.intersection(&d2).copied().collect();
    // If the fresh var's dep equals one side, FEx doesn't shrink (the
    // §6 dependency-cycle case). Signal no-progress so saturate falls
    // through to SFEx.
    if inter == d1 || inter == d2 {
        return None;
    }
    let x = f.n_vars + 1;
    f.add_existential(x, inter);
    let mut left = part.clone();
    left.push(x as Lit);
    left.sort_unstable();
    let mut right = c2;
    right.push(-(x as Lit));
    right.sort_unstable();
    Some((
        part,
        ForkResult {
            fresh: x,
            left,
            right,
        },
    ))
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

/// SFEx on `c` to *break a dependency cycle* (journal §6). Triggers when
/// FEx alone can't shrink any dep — i.e. every information-fork pair's
/// intersection equals one side. Picks an existential `a` whose dep is
/// minimal but not ⊆ any other existential's dep, picks `c3 = {u}` for
/// some universal `u ∈ dep(rest) \ dep(a)`, so the fresh var's dep is
/// `dep(a) ∩ dep(rest) \ {u}` — strictly smaller than `dep(a)`. Two
/// applications with complementary `c3` per Lemma `lem:elimstrongforks`
/// suffice to eliminate any strong fork; saturate naturally finds the
/// second on a later pass.
pub fn choose_sfork(f: &mut Formula, c: &Clause) -> Option<(Clause, Vec<Lit>, ForkResult)> {
    let exs: Vec<Var> = c
        .iter()
        .map(|&l| var(l))
        .filter(|&v| f.is_existential(v))
        .collect();
    if exs.len() < 2 {
        return None;
    }
    // Pick `a` with smallest dep (ties → first).
    let a = *exs.iter().min_by_key(|&&v| f.deps[&v].len())?;
    let da = f.deps[&a].clone();
    let part: Clause = c
        .iter()
        .copied()
        .filter(|&l| var(l) == a || f.dep(var(l)).is_subset(&da))
        .collect();
    let part_set: BTreeSet<Lit> = part.iter().copied().collect();
    let c2: Clause = c.iter().copied().filter(|l| !part_set.contains(l)).collect();
    if c2.is_empty() {
        return None;
    }
    let d1 = f.clause_dep(&part);
    let d2 = f.clause_dep(&c2);
    let inter: BTreeSet<Var> = d1.intersection(&d2).copied().collect();
    // FEx would give dep = inter. To shrink, drop one universal in inter
    // that's also in d2 (so the c3 lit is "covered" by rest's dep).
    let u = *inter.iter().find(|u| d2.contains(u))?;
    let c3: Vec<Lit> = vec![u as Lit];
    let x = f.n_vars + 1;
    let new_dep: BTreeSet<Var> = inter.iter().copied().filter(|&v| v != u).collect();
    if new_dep.len() >= da.len() {
        // No shrink — SFEx wouldn't make progress here.
        return None;
    }
    f.add_existential(x, new_dep);
    let mut left: Clause = c3.iter().copied().chain(part.iter().copied()).collect();
    left.push(x as Lit);
    left.sort_unstable();
    left.dedup();
    let mut right: Clause = c3.iter().copied().chain(c2.iter().copied()).collect();
    right.push(-(x as Lit));
    right.sort_unstable();
    right.dedup();
    Some((part, c3, ForkResult { fresh: x, left, right }))
}
