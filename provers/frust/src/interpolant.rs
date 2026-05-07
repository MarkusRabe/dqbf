//! McMillan interpolation from a CDCL proof.
//!
//! Partition the UNSAT clause set into A∧B. The interpolant I satisfies
//! A ⊨ I, I∧B ⊨ ⊥, vars(I) ⊆ vars(A)∩vars(B). For Padoa
//! (`A = matrix ∧ y`, `B = matrix' ∧ links(dep y) ∧ ¬y'`), I is a
//! definition of y over dep(y).
//!
//! McMillan's system (asymmetric, CAV'03):
//!   axiom C ∈ A → p(C) = ⋁{l ∈ C : var(l) shared}
//!   axiom C ∈ B → p(C) = ⊤
//!   resolve(C₁, C₂, x):
//!     x A-local → p = p(C₁) ∨ p(C₂)
//!     else      → p = p(C₁) ∧ p(C₂)
//!
//! References: McMillan, CAV'03; Slivovsky, SAT'20.

use crate::cdcl::Cdcl;
use crate::formula::{var, Lit, Var};
use std::collections::{HashMap, HashSet};

/// Tiny structurally-hashed AIG. Lit 0=⊥, 1=⊤; even=positive, lsb=neg.
/// Node IDs are allocated from a single counter so inputs added after a
/// gate never collide with that gate's lit.
pub struct Itp {
    pub inputs: Vec<Var>,
    in_lit: HashMap<Var, u32>,
    pub gates: Vec<(u32, u32)>,
    /// node[i]: None=input (find via inputs[..]); Some(k)=gates[k].
    node: Vec<Option<usize>>,
    strash: HashMap<(u32, u32), u32>,
}

impl Itp {
    pub fn new() -> Self {
        Self {
            inputs: Vec::new(),
            in_lit: HashMap::new(),
            gates: Vec::new(),
            node: Vec::new(),
            strash: HashMap::new(),
        }
    }
    fn alloc(&mut self) -> u32 {
        self.node.push(None);
        2 * self.node.len() as u32
    }
    fn input(&mut self, v: Var) -> u32 {
        if let Some(&l) = self.in_lit.get(&v) {
            return l;
        }
        let l = self.alloc();
        self.inputs.push(v);
        self.in_lit.insert(v, l);
        l
    }
    pub fn lit(&mut self, l: Lit) -> u32 {
        let p = self.input(var(l));
        if l > 0 {
            p
        } else {
            p ^ 1
        }
    }
    pub fn mk_and(&mut self, a: u32, b: u32) -> u32 {
        if a == 0 || b == 0 {
            return 0;
        }
        if a == 1 {
            return b;
        }
        if b == 1 {
            return a;
        }
        if a == b {
            return a;
        }
        if a == (b ^ 1) {
            return 0;
        }
        let k = if a < b { (a, b) } else { (b, a) };
        if let Some(&g) = self.strash.get(&k) {
            return g;
        }
        let g = self.alloc();
        self.gates.push(k);
        *self.node.last_mut().unwrap() = Some(self.gates.len() - 1);
        self.strash.insert(k, g);
        g
    }
    pub fn mk_or(&mut self, a: u32, b: u32) -> u32 {
        self.mk_and(a ^ 1, b ^ 1) ^ 1
    }
    pub fn node_kind(&self, l: u32) -> NodeKind {
        if l < 2 {
            return NodeKind::Const;
        }
        let i = (l >> 1) as usize - 1;
        match self.node[i] {
            None => {
                let pos = self
                    .inputs
                    .iter()
                    .position(|&v| self.in_lit[&v] == (l & !1))
                    .unwrap();
                NodeKind::Input(pos)
            }
            Some(k) => NodeKind::Gate(k),
        }
    }
    /// Evaluate at an assignment to `inputs` (bit i = value of inputs[i]).
    /// (Method named `eval` is AIG evaluation, not code-exec eval.)
    pub fn eval(&self, root: u32, assign: u64) -> bool {
        let mut val = vec![false; self.node.len() + 1];
        for (i, &v) in self.inputs.iter().enumerate() {
            val[(self.in_lit[&v] >> 1) as usize] = (assign >> i) & 1 == 1;
        }
        let lv = |l: u32, val: &[bool]| -> bool {
            if l < 2 {
                return l == 1;
            }
            val[(l >> 1) as usize] ^ (l & 1 == 1)
        };
        for (i, k) in self.node.iter().enumerate() {
            if let Some(gi) = k {
                let (a, b) = self.gates[*gi];
                val[i + 1] = lv(a, &val) && lv(b, &val);
            }
        }
        lv(root, &val)
    }
}

pub enum NodeKind {
    Const,
    Input(usize),
    Gate(usize),
}

#[derive(Clone, Copy, PartialEq)]
pub enum Side {
    A,
    B,
}

/// Extract the interpolant from `cdcl`'s proof log. `side(cr)` labels
/// each *input* cref; `shared` is the A∩B vocabulary; `a_local(v)` is
/// true iff v occurs only in A-side clauses.
pub fn mcmillan(
    cdcl: &Cdcl,
    side: impl Fn(u32) -> Side,
    shared: &HashSet<Var>,
    a_local: impl Fn(Var) -> bool,
) -> Option<(Itp, u32)> {
    let pl = cdcl.proof.as_ref()?;
    if pl.final_chain.is_empty() {
        return None;
    }
    let mut itp = Itp::new();
    let mut memo: HashMap<u32, u32> = HashMap::new();

    // Stack-based post-order over the proof DAG (recursion would blow
    // the stack on deep chains).
    let mut order: Vec<u32> = Vec::new();
    let mut seen: HashSet<u32> = HashSet::new();
    let mut stack: Vec<u32> = pl.final_chain.iter().map(|&(c, _)| c).collect();
    while let Some(cr) = stack.pop() {
        if !seen.insert(cr) {
            continue;
        }
        order.push(cr);
        if let Some(chain) = pl.ante.get(&cr) {
            for &(c, _) in chain {
                if !seen.contains(&c) {
                    stack.push(c);
                }
            }
        }
    }
    // Process in reverse (leaves first).
    for &cr in order.iter().rev() {
        if memo.contains_key(&cr) {
            continue;
        }
        let p = if let Some(chain) = pl.ante.get(&cr) {
            if chain.is_empty() {
                return None;
            }
            let mut acc = *memo.get(&chain[0].0)?;
            for &(c, pivot) in &chain[1..] {
                let q = *memo.get(&c)?;
                acc = if a_local(pivot) {
                    itp.mk_or(acc, q)
                } else {
                    itp.mk_and(acc, q)
                };
            }
            acc
        } else {
            match side(cr) {
                Side::B => 1,
                Side::A => {
                    let lits: Vec<u32> = cdcl
                        .clause_lits(cr)
                        .iter()
                        .filter(|&&l| shared.contains(&var(l)))
                        .map(|&l| itp.lit(l))
                        .collect();
                    lits.iter().fold(0u32, |a, &l| itp.mk_or(a, l))
                }
            }
        };
        memo.insert(cr, p);
    }
    // Fold the final chain.
    let mut acc = *memo.get(&pl.final_chain[0].0)?;
    for &(c, pivot) in &pl.final_chain[1..] {
        let q = *memo.get(&c)?;
        acc = if a_local(pivot) {
            itp.mk_or(acc, q)
        } else {
            itp.mk_and(acc, q)
        };
    }
    Some((itp, acc))
}
