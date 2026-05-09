//! SAT certificate check: substitute the AIGER's existential outputs
//! into the formula and ask whether the negation is UNSAT.
//!
//! Steps:
//!   1. Map AIGER inputs `i<k> u<id>` → universal vars; AIGER outputs
//!      `o<k> e<id>` → existential vars. Reject any mismatch.
//!   2. Cone check: each output's structural input cone ⊆ dep(e<id>).
//!   3. Tseitin the AIGER into CNF. Build the miter: for each input
//!      clause C, ¬C with existentials replaced by their output
//!      literals. The big disjunction "some clause violated" must be
//!      UNSAT for VALID.
//!   4. Hand the CNF to an external SAT solver (kissat).

use crate::aiger::Aag;
use crate::dqdimacs::{Formula, Var};
use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;
use std::path::Path;

#[derive(Debug, PartialEq)]
pub enum Verdict {
    Valid,
    Invalid(String),
    DepViolation(String),
}

pub fn verify(f: &Formula, aag: &Aag, sat_solver: &Path, scratch: &Path) -> Verdict {
    // ── 1. Symbol maps ──────────────────────────────────────────────
    let mut input_var: Vec<Option<Var>> = vec![None; aag.inputs.len()];
    let mut universal_input: BTreeMap<Var, usize> = BTreeMap::new();
    for k in 0..aag.inputs.len() {
        let name = match aag.symbols.get(&(b'i', k)) {
            Some(n) => n,
            None => return Verdict::Invalid(format!("input {k} has no symbol")),
        };
        let u = match parse_sym(name, 'u') {
            Some(u) => u,
            None => return Verdict::Invalid(format!("input symbol '{name}' is not 'u<id>'")),
        };
        if !f.is_universal(u) {
            return Verdict::Invalid(format!("input symbol u{u} is not a universal"));
        }
        if universal_input.contains_key(&u) {
            return Verdict::Invalid(format!("universal {u} mapped to two inputs"));
        }
        input_var[k] = Some(u);
        universal_input.insert(u, k);
    }
    let mut output_existential: BTreeMap<Var, usize> = BTreeMap::new();
    for k in 0..aag.outputs.len() {
        let name = match aag.symbols.get(&(b'o', k)) {
            Some(n) => n,
            None => return Verdict::Invalid(format!("output {k} has no symbol")),
        };
        let y = match parse_sym(name, 'e') {
            Some(y) => y,
            None => return Verdict::Invalid(format!("output symbol '{name}' is not 'e<id>'")),
        };
        if !f.is_existential(y) {
            return Verdict::Invalid(format!("output symbol e{y} is not an existential"));
        }
        if output_existential.contains_key(&y) {
            return Verdict::Invalid(format!("existential {y} mapped to two outputs"));
        }
        output_existential.insert(y, k);
    }

    // ── 2. Structural cone check ────────────────────────────────────
    // For each AIGER var, compute the set of input *vars* in its cone.
    // Detect cycles (RISKS C8).
    let mut gate_of: BTreeMap<u64, (u64, u64)> = BTreeMap::new();
    for &(lhs, r0, r1) in &aag.gates {
        gate_of.insert(lhs >> 1, (r0, r1));
    }
    // 0 = unvisited, 1 = on stack, 2 = done
    let max_v = aag.max_var as usize;
    let mut state = vec![0u8; max_v + 1];
    let mut cone: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); max_v + 1];
    // Mark inputs' cones as themselves.
    let input_pos: BTreeMap<u64, usize> = aag.inputs.iter().enumerate().map(|(k, &l)| (l >> 1, k)).collect();
    // Iterative DFS to avoid stack overflow.
    fn dfs(
        v: u64,
        gate_of: &BTreeMap<u64, (u64, u64)>,
        input_pos: &BTreeMap<u64, usize>,
        state: &mut [u8],
        cone: &mut [BTreeSet<usize>],
    ) -> Result<(), String> {
        let mut stack = vec![(v, 0u8)];
        while let Some(&(cur, phase)) = stack.last() {
            if phase == 0 {
                if state[cur as usize] == 1 {
                    return Err(format!("aiger cycle at var {cur}"));
                }
                if state[cur as usize] == 2 {
                    stack.pop();
                    continue;
                }
                state[cur as usize] = 1;
                stack.last_mut().unwrap().1 = 1;
                if let Some(&(r0, r1)) = gate_of.get(&cur) {
                    stack.push((r1 >> 1, 0));
                    stack.push((r0 >> 1, 0));
                }
                // Inputs and constant (0) have no children.
            } else {
                state[cur as usize] = 2;
                stack.pop();
                if let Some(&p) = input_pos.get(&cur) {
                    cone[cur as usize].insert(p);
                } else if let Some(&(r0, r1)) = gate_of.get(&cur) {
                    let a: BTreeSet<usize> = cone[(r0 >> 1) as usize].clone();
                    let b: &BTreeSet<usize> = &cone[(r1 >> 1) as usize];
                    cone[cur as usize] = a.union(b).copied().collect();
                }
                // Constant 0 / undefined-but-constant: empty cone.
            }
        }
        Ok(())
    }
    for (&y, &k) in &output_existential {
        let lit = aag.outputs[k];
        let v = lit >> 1;
        if v > aag.max_var {
            return Verdict::Invalid(format!("output {k} literal out of range"));
        }
        if let Err(e) = dfs(v, &gate_of, &input_pos, &mut state, &mut cone) {
            return Verdict::Invalid(e);
        }
        let dep = &f.deps[&y];
        for &p in &cone[v as usize] {
            let u = input_var[p].unwrap();
            if !dep.contains(&u) {
                return Verdict::DepViolation(format!(
                    "output e{y}'s cone reads input u{u} ∉ dep(e{y})"
                ));
            }
        }
    }

    // ── 3. Build the miter CNF ──────────────────────────────────────
    // Variables: 1..n_univ for universals, then one per AIGER gate
    // output, then any clause-aux.
    // The mapping is: cnf_var(universal) and cnf_lit(aiger_lit).
    let mut cnf: Vec<Vec<i64>> = Vec::new();
    let mut next_var: i64 = 0;
    let mut univ_cnf: BTreeMap<Var, i64> = BTreeMap::new();
    for (&u, &_k) in &universal_input {
        next_var += 1;
        univ_cnf.insert(u, next_var);
    }
    // Universals in the formula but not in the .aag input list still
    // need a CNF variable for free occurrences in clauses (RISKS C7).
    for &u in &f.universals {
        univ_cnf.entry(u).or_insert_with(|| {
            next_var += 1;
            next_var
        });
    }
    // Map each AIGER var to a CNF var. Constant 0 is special.
    let mut aig_cnf: Vec<i64> = vec![0; max_v + 1];
    for &lit in &aag.inputs {
        let v = (lit >> 1) as usize;
        let u = input_var[input_pos[&(lit as u64 >> 1)]].unwrap();
        aig_cnf[v] = univ_cnf[&u];
    }
    for &(lhs, _, _) in &aag.gates {
        next_var += 1;
        aig_cnf[(lhs >> 1) as usize] = next_var;
    }
    // Constant true literal: a fresh CNF var forced to true.
    next_var += 1;
    let cnf_true = next_var;
    cnf.push(vec![cnf_true]);
    // Translate an AIGER lit to a CNF lit.
    let aig_lit = |l: u64| -> i64 {
        if l == 0 {
            return -cnf_true;
        }
        if l == 1 {
            return cnf_true;
        }
        let v = (l >> 1) as usize;
        let base = aig_cnf[v];
        if base == 0 {
            // Undefined var: treat as constant false (the AIGER spec
            // permits free literals in unstructured files, but a cert
            // shouldn't have them — be conservative and reject).
            return 0; // signal: caller must reject
        }
        if l & 1 == 1 {
            -base
        } else {
            base
        }
    };
    // Gate definitions: g ↔ a∧b.
    for &(lhs, r0, r1) in &aag.gates {
        let g = aig_lit(lhs);
        let a = aig_lit(r0);
        let b = aig_lit(r1);
        if g == 0 || a == 0 || b == 0 {
            return Verdict::Invalid("aiger literal references undefined var".into());
        }
        cnf.push(vec![-g, a]);
        cnf.push(vec![-g, b]);
        cnf.push(vec![g, -a, -b]);
    }
    // CNF lit for an existential: its output's gate lit. For a defined
    // existential not mapped to an output, the cert is incomplete.
    let exist_cnf = |y: Var| -> Option<i64> {
        output_existential.get(&y).map(|&k| aig_lit(aag.outputs[k]))
    };
    // Are all existentials that occur in some clause covered?
    let mut live: BTreeSet<Var> = BTreeSet::new();
    for c in &f.clauses {
        for &l in c {
            let v = l.abs();
            if f.is_existential(v) {
                live.insert(v);
            }
        }
    }
    for &y in &live {
        if exist_cnf(y).is_none() {
            return Verdict::Invalid(format!("existential e{y} occurs in a clause but has no output"));
        }
    }
    // Miter: for each clause C, an aux v_C ↔ "C is violated" =
    //   ∧_{l∈C} ¬lit(l). Then the big clause ⋁ v_C. UNSAT ⇒ no
    //   universal assignment can violate any clause ⇒ VALID.
    let mut viol: Vec<i64> = Vec::with_capacity(f.clauses.len());
    for c in &f.clauses {
        next_var += 1;
        let v = next_var;
        let mut lits: Vec<i64> = Vec::with_capacity(c.len());
        for &l in c {
            let var = l.abs();
            let base = if f.is_existential(var) {
                exist_cnf(var).unwrap()
            } else if f.is_universal(var) {
                univ_cnf[&var]
            } else {
                // Unquantified var that occurs in a clause — give it a
                // fresh CNF var (it's universally quantified by
                // default in the miter, which is the conservative
                // choice).
                next_var += 1;
                next_var
            };
            if base == 0 {
                return Verdict::Invalid("miter: zero CNF lit".into());
            }
            lits.push(if l < 0 { -base } else { base });
        }
        // v → ¬l for each l.
        for &l in &lits {
            cnf.push(vec![-v, -l]);
        }
        // ¬v → some l.
        let mut back = vec![v];
        back.extend(&lits);
        cnf.push(back);
        viol.push(v);
    }
    cnf.push(viol);

    // ── 4. Call the SAT solver ──────────────────────────────────────
    let cnf_path = scratch.join("verify_rs_miter.cnf");
    let mut out = match std::fs::File::create(&cnf_path) {
        Ok(f) => f,
        Err(e) => return Verdict::Invalid(format!("write cnf: {e}")),
    };
    if writeln!(out, "p cnf {} {}", next_var, cnf.len()).is_err() {
        return Verdict::Invalid("write cnf header".into());
    }
    for c in &cnf {
        let mut line = String::new();
        for &l in c {
            line.push_str(&l.to_string());
            line.push(' ');
        }
        line.push('0');
        if writeln!(out, "{line}").is_err() {
            return Verdict::Invalid("write cnf body".into());
        }
    }
    drop(out);
    let result = std::process::Command::new(sat_solver)
        .arg(&cnf_path)
        .output();
    match result {
        Ok(o) => {
            let txt = String::from_utf8_lossy(&o.stdout);
            // SAT solver convention: exit 10 = SAT, 20 = UNSAT, 0 = unknown.
            if txt.contains("s UNSATISFIABLE") || o.status.code() == Some(20) {
                Verdict::Valid
            } else if txt.contains("s SATISFIABLE") || o.status.code() == Some(10) {
                Verdict::Invalid("miter is satisfiable (counterexample exists)".into())
            } else {
                Verdict::Invalid(format!("sat solver gave no answer (status {:?})", o.status.code()))
            }
        }
        Err(e) => Verdict::Invalid(format!("sat solver failed: {e}")),
    }
}

fn parse_sym(s: &str, prefix: char) -> Option<Var> {
    let s = s.strip_prefix(prefix)?;
    s.parse::<Var>().ok().filter(|&v| v > 0)
}
