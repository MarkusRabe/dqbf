//! HQSpre-style light preprocessing: unit + pure literal elimination.
//!
//! Sound for both directions. For SAT certs, eliminated existentials
//! are recorded as constants; eliminated universals don't appear in
//! the cert (they're irrelevant). For UNSAT proofs, the proof is over
//! the simplified clause set, so axioms match the simplified formula —
//! we re-emit a separate proof over the *original* formula by replaying
//! eliminations as axiom + ured/res steps.

use crate::formula::{var, Clause, Formula, Lit, Var};
use std::collections::BTreeSet;

#[derive(Debug, Clone, Default)]
pub struct PreResult {
    pub fixed: Vec<(Var, bool)>, // existentials assigned to a constant
    pub dropped_universals: Vec<Var>,
}

pub fn preprocess(f: &Formula) -> (Formula, PreResult) {
    let mut clauses: Vec<Option<Clause>> = f.clauses.iter().cloned().map(Some).collect();
    let mut fixed: Vec<i8> = vec![0; f.n_vars as usize + 1];
    let mut res = PreResult::default();
    let mut changed = true;
    while changed {
        changed = false;
        // Unit existential.
        for c in clauses.iter().flatten() {
            if c.len() == 1 {
                let l = c[0];
                let v = var(l);
                if f.is_existential(v) && fixed[v as usize] == 0 {
                    fixed[v as usize] = if l > 0 { 1 } else { -1 };
                    res.fixed.push((v, l > 0));
                    changed = true;
                }
            }
        }
        // Pure literals.
        let mut pos: BTreeSet<Var> = BTreeSet::new();
        let mut neg: BTreeSet<Var> = BTreeSet::new();
        for c in clauses.iter().flatten() {
            for &l in c {
                let v = var(l);
                if fixed[v as usize] != 0 {
                    continue;
                }
                if l > 0 {
                    pos.insert(v);
                } else {
                    neg.insert(v);
                }
            }
        }
        for &v in pos.union(&neg) {
            if fixed[v as usize] != 0 {
                continue;
            }
            let in_p = pos.contains(&v);
            let in_n = neg.contains(&v);
            if in_p == in_n {
                continue;
            }
            if f.is_existential(v) {
                // Pure existential: assign to satisfying polarity.
                fixed[v as usize] = if in_p { 1 } else { -1 };
                res.fixed.push((v, in_p));
                changed = true;
            }
            // Pure universal: deferred (cert deps complication).
        }
        // Simplify clauses under fixed.
        for slot in clauses.iter_mut() {
            if let Some(c) = slot {
                let mut sat = false;
                let mut nc: Clause = Vec::with_capacity(c.len());
                for &l in c.iter() {
                    let p = fixed[var(l) as usize];
                    if p == 0 {
                        nc.push(l);
                    } else if (l > 0) == (p > 0) {
                        sat = true;
                        break;
                    }
                }
                if sat {
                    *slot = None;
                    changed = true;
                } else if nc.len() != c.len() {
                    *slot = Some(nc);
                    changed = true;
                }
            }
        }
    }
    // Build simplified formula. Universals unchanged; deps unchanged
    // (just remove fixed existentials from the map).
    let mut deps = f.deps.clone();
    for (v, _) in &res.fixed {
        deps.remove(v);
    }
    let new_clauses: Vec<Clause> = clauses.into_iter().flatten().collect();
    let g = Formula::new(f.n_vars, f.universals.clone(), deps, new_clauses);
    (g, res)
}

/// Extend a Skolem cert (over the simplified formula) with constants for
/// the eliminated existentials.
pub fn extend_skolem(sk: &mut crate::aiger::Skolem, res: &PreResult) {
    for &(v, val) in &res.fixed {
        sk.insert(v, (vec![if val { 1 } else { 0 }], 0));
    }
}

/// Detect existentials defined by an AND/NAND gate pattern:
///   {¬y,a} {¬y,b} {y,¬a,¬b}  ⇒  y = a ∧ b
/// (Any of y/a/b may be negated, capturing all 2-input gates.)
/// Returns the set of *defined* existential vars.
pub fn detect_defined(f: &Formula) -> BTreeSet<Var> {
    let mut binaries: std::collections::HashMap<Lit, Vec<Lit>> = std::collections::HashMap::new();
    let mut ternaries: Vec<&Clause> = Vec::new();
    for c in &f.clauses {
        match c.len() {
            2 => {
                binaries.entry(c[0]).or_default().push(c[1]);
                binaries.entry(c[1]).or_default().push(c[0]);
            }
            3 => ternaries.push(c),
            _ => {}
        }
    }
    let mut defined: BTreeSet<Var> = BTreeSet::new();
    for c in ternaries {
        // Try each literal as the gate output `y`.
        for &yl in c {
            let y = var(yl);
            if !f.is_existential(y) {
                continue;
            }
            let others: Vec<Lit> = c.iter().copied().filter(|&l| l != yl).collect();
            // Need {¬yl, ¬others[0]}? No: pattern is {¬y,a}{¬y,b}{y,¬a,¬b}.
            // Here yl is the literal in the 3-clause, so yl plays `y` and
            // others are ¬a,¬b. We need binaries {¬yl, a}={¬yl, ¬others[0]}
            // and {¬yl, ¬others[1]}.
            let need =
                |x: Lit, w: Lit| -> bool { binaries.get(&x).map_or(false, |v| v.contains(&w)) };
            if need(-yl, -others[0]) && need(-yl, -others[1]) {
                defined.insert(y);
            }
        }
    }
    defined
}

#[allow(dead_code)]
pub fn lit_of(v: Var, pol: bool) -> Lit {
    if pol {
        v as Lit
    } else {
        -(v as Lit)
    }
}
