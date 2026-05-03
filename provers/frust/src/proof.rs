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

    pub fn write_json<W: Write>(&self, w: &mut W) -> std::io::Result<()> {
        write!(w, "[")?;
        for (i, s) in self.steps.iter().enumerate() {
            if i > 0 {
                write!(w, ",")?;
            }
            write!(w, r#"{{"clause":{:?},"rule":"{}""#, s.clause, s.rule)?;
            write!(w, r#","premises":{:?}"#, s.premises)?;
            if let Some(p) = s.pivot {
                write!(w, r#","pivot":{}"#, p)?;
            } else {
                write!(w, r#","pivot":null"#)?;
            }
            match &s.part {
                Some(p) => write!(w, r#","part":{:?}"#, p)?,
                None => write!(w, r#","part":null"#)?,
            }
            match &s.c3 {
                Some(p) => write!(w, r#","c3":{:?}"#, p)?,
                None => write!(w, r#","c3":null"#)?,
            }
            match s.fresh {
                Some(p) => write!(w, r#","fresh":{}"#, p)?,
                None => write!(w, r#","fresh":null"#)?,
            }
            write!(w, "}}")?;
        }
        write!(w, "]")
    }
}
