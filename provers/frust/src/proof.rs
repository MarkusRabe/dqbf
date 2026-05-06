//! `.frp` JSON proof emission (matches `core/proof_trace.py`).

use crate::formula::{Clause, Lit, Var};
use std::io::Write;

#[derive(Debug, Clone)]
pub struct Step {
    pub clause: Vec<Lit>,
    pub rule: &'static str,
    pub premises: Vec<usize>,
    pub pivot: Option<Var>,
    pub part: Option<Vec<Lit>>,
    pub c3: Option<Vec<Lit>>,
    pub fresh: Option<Var>,
}

impl Step {
    fn new(clause: Vec<Lit>, rule: &'static str, premises: Vec<usize>) -> Self {
        Self {
            clause,
            rule,
            premises,
            pivot: None,
            part: None,
            c3: None,
            fresh: None,
        }
    }
    pub fn axiom(c: &Clause) -> Self {
        Self::new(c.clone(), "axiom", vec![])
    }
    pub fn ured(c: &Clause, from: usize) -> Self {
        Self::new(c.clone(), "ured", vec![from])
    }
    pub fn res(c: &Clause, a: usize, b: usize, pivot: Var) -> Self {
        let mut s = Self::new(c.clone(), "res", vec![a, b]);
        s.pivot = Some(pivot);
        s
    }
    pub fn fex(c: &Clause, src: usize, part: Vec<Lit>, fresh: Var) -> Self {
        let mut s = Self::new(c.clone(), "fex", vec![src]);
        s.part = Some(part);
        s.fresh = Some(fresh);
        s
    }
    pub fn sfex(c: &Clause, src: usize, part: Vec<Lit>, c3: Vec<Lit>, fresh: Var) -> Self {
        let mut s = Self::new(c.clone(), "sfex", vec![src]);
        s.part = Some(part);
        s.c3 = Some(c3);
        s.fresh = Some(fresh);
        s
    }
}

#[derive(Default)]
pub struct Proof {
    pub steps: Vec<Step>,
}

impl Proof {
    pub fn add(&mut self, s: Step) -> usize {
        self.steps.push(s);
        self.steps.len() - 1
    }

    /// Keep only steps reachable from the first ⊥ via `premises`. Saturate
    /// records every derived clause; only a fraction actually contributes
    /// to the refutation.
    pub fn compact(&mut self) {
        let n = self.steps.len();
        let root = match self.steps.iter().position(|s| s.clause.is_empty()) {
            Some(i) => i,
            None => return,
        };
        let mut keep = vec![false; n];
        let mut stack = vec![root];
        while let Some(i) = stack.pop() {
            if keep[i] {
                continue;
            }
            keep[i] = true;
            for &p in &self.steps[i].premises {
                if p < n && !keep[p] {
                    stack.push(p);
                }
            }
        }
        let mut new_idx = vec![usize::MAX; n];
        let mut out: Vec<Step> = Vec::new();
        for i in 0..=root {
            if !keep[i] {
                continue;
            }
            let mut s = self.steps[i].clone();
            for p in s.premises.iter_mut() {
                *p = new_idx[*p];
            }
            new_idx[i] = out.len();
            out.push(s);
        }
        self.steps = out;
    }

    pub fn write_json<W: Write>(&self, w: &mut W) -> std::io::Result<()> {
        write!(w, "[")?;
        for (i, s) in self.steps.iter().enumerate() {
            if i > 0 {
                write!(w, ",")?;
            }
            write!(w, r#"{{"clause":{:?},"rule":"{}""#, s.clause, s.rule)?;
            if !s.premises.is_empty() {
                write!(w, r#","premises":{:?}"#, s.premises)?;
            }
            if let Some(p) = s.pivot {
                write!(w, r#","pivot":{}"#, p)?;
            }
            if let Some(p) = &s.part {
                write!(w, r#","part":{:?}"#, p)?;
            }
            if let Some(p) = &s.c3 {
                write!(w, r#","c3":{:?}"#, p)?;
            }
            if let Some(p) = s.fresh {
                write!(w, r#","fresh":{}"#, p)?;
            }
            write!(w, "}}")?;
        }
        write!(w, "]")
    }
}
