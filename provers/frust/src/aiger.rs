//! Minimal .aag writer for Skolem certificates.

use crate::formula::{Formula, Var};
use std::collections::BTreeMap;
use std::io::Write;

pub type Skolem = BTreeMap<Var, BTreeMap<Vec<bool>, bool>>;

struct Aig {
    n_inputs: usize,
    gates: Vec<(u32, u32, u32)>,
}

impl Aig {
    fn lit_input(&self, i: usize) -> u32 {
        2 * (i as u32 + 1)
    }
    fn max_var(&self) -> u32 {
        self.n_inputs as u32 + self.gates.len() as u32
    }
    fn mk_and(&mut self, a: u32, b: u32) -> u32 {
        let v = self.max_var() + 1;
        self.gates.push((2 * v, a, b));
        2 * v
    }
    fn mk_or(&mut self, a: u32, b: u32) -> u32 {
        self.mk_and(a ^ 1, b ^ 1) ^ 1
    }
    fn mk_ite(&mut self, c: u32, t: u32, e: u32) -> u32 {
        let a = self.mk_and(c, t);
        let b = self.mk_and(c ^ 1, e);
        self.mk_or(a, b)
    }
}

fn shannon(aig: &mut Aig, tbl: &BTreeMap<Vec<bool>, bool>, inputs: &[u32]) -> u32 {
    fn rec(
        aig: &mut Aig,
        tbl: &BTreeMap<Vec<bool>, bool>,
        ins: &[u32],
        pre: &mut Vec<bool>,
    ) -> u32 {
        if pre.len() == ins.len() {
            return if tbl[pre] { 1 } else { 0 };
        }
        let sel = ins[pre.len()];
        pre.push(true);
        let t = rec(aig, tbl, ins, pre);
        pre.pop();
        pre.push(false);
        let e = rec(aig, tbl, ins, pre);
        pre.pop();
        aig.mk_ite(sel, t, e)
    }
    let mut pre = Vec::new();
    rec(aig, tbl, inputs, &mut pre)
}

pub fn write_skolem_aag<W: Write>(w: &mut W, f: &Formula, sk: &Skolem) -> std::io::Result<()> {
    let mut aig = Aig {
        n_inputs: f.universals.len(),
        gates: Vec::new(),
    };
    let u_lit: BTreeMap<Var, u32> = f
        .universals
        .iter()
        .enumerate()
        .map(|(i, &u)| (u, aig.lit_input(i)))
        .collect();
    let mut outputs: Vec<(Var, u32)> = Vec::new();
    for (&y, tbl) in sk {
        let deps: Vec<Var> = f.deps[&y].iter().copied().collect();
        let ins: Vec<u32> = deps.iter().map(|d| u_lit[d]).collect();
        let out = shannon(&mut aig, tbl, &ins);
        outputs.push((y, out));
    }
    let m = aig.max_var();
    writeln!(
        w,
        "aag {} {} 0 {} {}",
        m,
        aig.n_inputs,
        outputs.len(),
        aig.gates.len()
    )?;
    for i in 0..aig.n_inputs {
        writeln!(w, "{}", aig.lit_input(i))?;
    }
    for &(_, o) in &outputs {
        writeln!(w, "{}", o)?;
    }
    for &(g, a, b) in &aig.gates {
        writeln!(w, "{} {} {}", g, a, b)?;
    }
    for (i, &u) in f.universals.iter().enumerate() {
        writeln!(w, "i{} u{}", i, u)?;
    }
    for (i, &(y, _)) in outputs.iter().enumerate() {
        writeln!(w, "o{} e{}", i, y)?;
    }
    Ok(())
}
