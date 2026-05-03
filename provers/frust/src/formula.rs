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
}

impl Formula {
    pub fn new(
        n_vars: u32,
        universals: Vec<Var>,
        deps: BTreeMap<Var, BTreeSet<Var>>,
        clauses: Vec<Clause>,
    ) -> Self {
        let mut is_universal = vec![false; n_vars as usize + 1];
        for &u in &universals {
            is_universal[u as usize] = true;
        }
        Self {
            n_vars,
            universals,
            deps,
            clauses,
            is_universal,
        }
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
            self.n_vars = y;
        }
        self.deps.insert(y, d);
    }
}
