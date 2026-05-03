//! DQBF formula IR. Standalone — no shared code with the rest of the repo.

#![allow(dead_code)]
use std::collections::{BTreeMap, BTreeSet};

pub type Lit = i32;
pub type Var = u32;
/// Sorted, dedup'd vector of literals.
pub type Clause = Vec<Lit>;

#[inline]
pub fn var(l: Lit) -> Var {
    l.unsigned_abs()
}

#[inline]
pub fn clause_from(iter: impl IntoIterator<Item = Lit>) -> Clause {
    let mut v: Vec<Lit> = iter.into_iter().collect();
    v.sort_unstable();
    v.dedup();
    v
}

#[derive(Debug, Clone)]
pub struct Formula {
    pub n_vars: u32,
    pub universals: Vec<Var>,
    pub deps: BTreeMap<Var, BTreeSet<Var>>,
    pub clauses: Vec<Clause>,
    is_universal: Vec<bool>,
    /// dep_mask[y] bit u set iff existential y depends on universals[u].
    dep_mask: Vec<u64>,
}

impl Formula {
    pub fn new(
        n_vars: u32,
        universals: Vec<Var>,
        deps: BTreeMap<Var, BTreeSet<Var>>,
        clauses: Vec<Clause>,
    ) -> Self {
        let mut is_universal = vec![false; n_vars as usize + 1];
        let mut u_bit = vec![0u64; n_vars as usize + 1];
        for (i, &u) in universals.iter().enumerate() {
            is_universal[u as usize] = true;
            if i < 64 {
                u_bit[u as usize] = 1u64 << i;
            }
        }
        let mut dep_mask = vec![0u64; n_vars as usize + 1];
        for (&y, ds) in &deps {
            let mut m = 0u64;
            for &d in ds {
                m |= u_bit[d as usize];
            }
            dep_mask[y as usize] = m;
        }
        for &u in &universals {
            dep_mask[u as usize] = u_bit[u as usize];
        }
        Self {
            n_vars,
            universals,
            deps,
            clauses,
            is_universal,
            dep_mask,
        }
    }

    #[inline]
    pub fn dep_mask(&self, v: Var) -> u64 {
        self.dep_mask.get(v as usize).copied().unwrap_or(0)
    }

    #[inline]
    pub fn is_universal(&self, v: Var) -> bool {
        (v as usize) < self.is_universal.len() && self.is_universal[v as usize]
    }

    #[inline]
    pub fn is_existential(&self, v: Var) -> bool {
        self.deps.contains_key(&v)
    }

    pub fn dep(&self, v: Var) -> BTreeSet<Var> {
        if let Some(d) = self.deps.get(&v) {
            d.clone()
        } else {
            let mut s = BTreeSet::new();
            s.insert(v);
            s
        }
    }

    pub fn clause_dep(&self, c: &[Lit]) -> BTreeSet<Var> {
        let mut out = BTreeSet::new();
        for &l in c {
            out.extend(self.dep(var(l)));
        }
        out
    }

    pub fn add_existential(&mut self, y: Var, d: BTreeSet<Var>) {
        if y > self.n_vars {
            self.is_universal.resize(y as usize + 1, false);
            self.dep_mask.resize(y as usize + 1, 0);
            self.n_vars = y;
        }
        let mut m = 0u64;
        for (i, &u) in self.universals.iter().enumerate() {
            if i < 64 && d.contains(&u) {
                m |= 1u64 << i;
            }
        }
        self.dep_mask[y as usize] = m;
        self.deps.insert(y, d);
    }
}
