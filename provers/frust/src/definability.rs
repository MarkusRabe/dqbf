//! Padoa-style definability detection. An existential `y` is
//! *dep-definable* iff any two models of the matrix that agree on
//! `dep(y)` also agree on `y` — i.e. the matrix uniquely determines
//! `y` as a function of `dep(y)`.
//!
//! Check: build two copies of the matrix (vars 1..n and n+1..2n),
//! link `dep(y)` across copies via selector-guarded equiv clauses,
//! assume `y_A ∧ ¬y_B`. UNSAT ⇒ defined. Iterate to fixpoint,
//! additionally linking already-defined `z` with `dep(z) ⊆ dep(y)`
//! (sound: such `z` are functions of `dep(y)`, so linking them adds
//! no information beyond what linking `dep(y)` already implies).
//!
//! Reference: Slivovsky, "Interpolation-based semantic gate
//! extraction" (SAT'20); Reichl/Slivovsky/Szeider, "Pedant" (SAT'21).

use crate::cdcl::Cdcl;
use crate::formula::{var, Clause, Formula, Lit, Var};
use crate::interpolant::{mcmillan, Itp, Side};
use std::collections::{BTreeSet, HashMap, HashSet};

pub struct DefSplit {
    pub defined: Vec<Var>,
    pub undefined: Vec<Var>,
}

pub struct Def {
    pub itp: Itp,
    pub root: u32,
}

/// Padoa fixpoint with selector-guarded link clauses so a single
/// incremental CDCL instance serves all per-y checks. Returns `None`
/// if the budget runs out before converging.
pub fn padoa_split(
    f: &Formula,
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
) -> Option<DefSplit> {
    let n = f.n_vars as Lit;
    let shift = |l: Lit| -> Lit { if l > 0 { l + n } else { l - n } };

    // Var layout:
    //   1..n         copy A
    //   n+1..2n      copy B
    //   2n+1..       one selector per var (universal or existential)
    let link_vars: Vec<Var> = {
        let mut v: Vec<Var> = f.universals.iter().copied().collect();
        v.extend(f.deps.keys().copied());
        v.sort_unstable();
        v
    };
    let sel: HashMap<Var, Lit> = link_vars
        .iter()
        .enumerate()
        .map(|(i, &v)| (v, 2 * n + 1 + i as Lit))
        .collect();
    let total_vars = 2 * n as usize + link_vars.len();

    let mut clauses: Vec<Clause> =
        Vec::with_capacity(2 * f.clauses.len() + 2 * link_vars.len());
    for c in &f.clauses {
        clauses.push(c.clone());
        clauses.push(c.iter().map(|&l| shift(l)).collect());
    }
    for &v in &link_vars {
        let s = sel[&v];
        let a = v as Lit;
        let b = shift(a);
        clauses.push(vec![-s, -a, b]);
        clauses.push(vec![-s, a, -b]);
    }
    let mut cdcl = Cdcl::new(total_vars, &clauses);
    let mut model = vec![0i8; total_vars + 1];

    let live: HashSet<Var> = f
        .clauses
        .iter()
        .flat_map(|c| c.iter().map(|&l| var(l)))
        .filter(|v| f.deps.contains_key(v))
        .collect();
    let deps: HashMap<Var, BTreeSet<Var>> = f
        .deps
        .iter()
        .map(|(&y, d)| (y, d.clone()))
        .collect();

    let mut defined: Vec<Var> = f
        .deps
        .keys()
        .copied()
        .filter(|y| !live.contains(y))
        .collect();
    let mut is_defined: HashSet<Var> = defined.iter().copied().collect();
    let mut todo: Vec<Var> = live.iter().copied().collect();
    todo.sort_by_key(|y| deps[y].len());

    let budget_per = ((1_000_000 / live.len().max(1)) as u64).max(500);
    let mut rounds = 0usize;
    loop {
        rounds += 1;
        let mut still: Vec<Var> = Vec::new();
        let mut progress = false;
        for &y in &todo {
            if start.elapsed().as_secs_f64() >= deadline {
                if debug {
                    eprintln!(
                        "c [def] padoa deadline: round {}, defined {}, pending {}",
                        rounds,
                        defined.len(),
                        still.len()
                    );
                }
                return None;
            }
            let dy = &deps[&y];
            let mut assump: Vec<Lit> = Vec::with_capacity(2 + dy.len());
            assump.push(y as Lit);
            assump.push(-shift(y as Lit));
            for &u in dy {
                assump.push(sel[&u]);
            }
            for &z in &defined {
                if z != y && deps.get(&z).map_or(true, |dz| dz.is_subset(dy)) {
                    assump.push(sel[&z]);
                }
            }
            let sat = cdcl.solve(&assump, &mut model, budget_per);
            if cdcl.budget_hit {
                still.push(y);
                continue;
            }
            if sat {
                still.push(y);
            } else {
                defined.push(y);
                is_defined.insert(y);
                progress = true;
            }
        }
        todo = still;
        if !progress || todo.is_empty() {
            break;
        }
    }
    if debug {
        eprintln!(
            "c [def] padoa: {} rounds, {} defined, {} undefined",
            rounds,
            defined.len(),
            todo.len()
        );
    }
    Some(DefSplit {
        defined,
        undefined: todo,
    })
}

/// For each `y` in `defined`, extract a McMillan interpolant `I(dep(y))`
/// such that `y ↔ I` under the matrix. Uses one fresh proof-logging
/// CDCL per y (no selector gating, so the proof's shared vocabulary is
/// exactly dep(y)). Skips y when it isn't defined over dep(y) *alone*
/// (i.e. needs the linked-z fixpoint) — those still go through CEGAR.
pub fn extract_interpolants(
    f: &Formula,
    defined: &[Var],
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
) -> HashMap<Var, Def> {
    let n = f.n_vars as Lit;
    let m = f.clauses.len();
    let nu = n as Var;
    let shift = |l: Lit| -> Lit { if l > 0 { l + n } else { l - n } };
    let live: HashSet<Var> = f
        .clauses
        .iter()
        .flat_map(|c| c.iter().map(|&l| var(l)))
        .collect();
    let mut order: Vec<Var> = defined.iter().copied().filter(|y| live.contains(y)).collect();
    order.sort_by_key(|y| f.deps[y].len());
    let mut out: HashMap<Var, Def> = HashMap::new();
    let mut model = vec![0i8; 2 * n as usize + 1];
    let mut base: Vec<Clause> = Vec::with_capacity(2 * m);
    for c in &f.clauses {
        base.push(c.clone());
    }
    for c in &f.clauses {
        base.push(c.iter().map(|&l| shift(l)).collect());
    }
    // Fixpoint: each pass links z's already in `out`, so the reference
    // graph stays acyclic and self-contained. A y that needs a same-dep z
    // fails on pass 1 but succeeds on pass 2 once z is in `out`.
    'passes: loop {
        let before = out.len();
    for &y in &order {
        if out.contains_key(&y) {
            continue;
        }
        if start.elapsed().as_secs_f64() >= deadline {
            break 'passes;
        }
        let dy: BTreeSet<Var> = f.deps[&y].clone();
        let linked_z: Vec<Var> = out
            .keys()
            .copied()
            .filter(|&z| f.deps[&z].is_subset(&dy))
            .collect();
        let mut clauses = base.clone();
        for &u in dy.iter().chain(linked_z.iter()) {
            let a = u as Lit;
            let b = shift(a);
            clauses.push(vec![-a, b]);
            clauses.push(vec![a, -b]);
        }
        let mut cdcl = Cdcl::new(2 * n as usize, &clauses);
        cdcl.enable_proof_log();
        let unsat = !cdcl.solve(&[y as Lit, -shift(y as Lit)], &mut model, 50_000);
        if cdcl.budget_hit || !unsat {
            continue;
        }
        let shared: HashSet<Var> = dy.iter().chain(linked_z.iter()).copied().collect();
        let side = |cr: u32| -> Side {
            if cdcl.clause_lits(cr).iter().all(|&l| var(l) <= nu) {
                Side::A
            } else {
                Side::B
            }
        };
        let a_local = |v: Var| v <= nu && !shared.contains(&v);
        if let Some((itp, root)) = mcmillan(&cdcl, side, &shared, a_local) {
            out.insert(y, Def { itp, root });
        }
    }
        if out.len() == before {
            break;
        }
    }
    if debug {
        eprintln!(
            "c [def] interpolants: {}/{} extracted (gates: {})",
            out.len(),
            defined.len(),
            out.values().map(|d| d.itp.gates.len()).sum::<usize>()
        );
    }
    out
}

/// Cross-check each interpolant against the matrix at `k` random rows.
pub fn validate_interpolants(
    f: &Formula,
    defs: &HashMap<Var, Def>,
    k: usize,
) -> Option<(Var, Vec<Lit>)> {
    let n = f.n_vars as usize;
    let mut cdcl = Cdcl::new(n, &f.clauses);
    let mut model = vec![0i8; n + 1];
    // Evaluate all interpolants at row `urow` (recursive over linked-z).
    fn eval_at(
        y: Var,
        urow: &HashMap<Var, bool>,
        defs: &HashMap<Var, Def>,
        memo: &mut HashMap<Var, bool>,
    ) -> Option<bool> {
        if let Some(&v) = memo.get(&y) {
            return Some(v);
        }
        let d = defs.get(&y)?;
        let mut a = 0u64;
        for (i, &v) in d.itp.inputs.iter().enumerate() {
            let bit = if let Some(&b) = urow.get(&v) {
                b
            } else {
                eval_at(v, urow, defs, memo)?
            };
            if bit {
                a |= 1 << i;
            }
        }
        let r = d.itp.eval(d.root, a);
        memo.insert(y, r);
        Some(r)
    }
    let mut seed = 0x5eed_u64;
    for _ in 0..k {
        seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
        let urow: HashMap<Var, bool> = f
            .universals
            .iter()
            .enumerate()
            .map(|(i, &u)| (u, (seed >> (i % 60)) & 1 == 1))
            .collect();
        let assump: Vec<Lit> = urow
            .iter()
            .map(|(&u, &b)| if b { u as Lit } else { -(u as Lit) })
            .collect();
        if !cdcl.solve(&assump, &mut model, 100_000) {
            continue;
        }
        let mut memo = HashMap::new();
        // Check in dependency order so the first mismatch is the root cause.
        let mut order: Vec<Var> = defs.keys().copied().collect();
        order.sort_by_key(|y| f.deps[y].len());
        for &y in &order {
            // First check inputs are consistent (so we report the *root*).
            let d = &defs[&y];
            let mut ok = true;
            for &v in &d.itp.inputs {
                if defs.contains_key(&v) {
                    if let Some(iv) = eval_at(v, &urow, defs, &mut memo) {
                        if iv != (model[v as usize] > 0) {
                            ok = false;
                        }
                    }
                }
            }
            if !ok {
                continue;
            }
            if let Some(iv) = eval_at(y, &urow, defs, &mut memo) {
                let mv = model[y as usize] > 0;
                if iv != mv {
                    eprintln!(
                        "  validate: y={} itp={} model={} inputs_mv={:?}",
                        y, iv, mv,
                        d.itp.inputs.iter().map(|&v| (v, model[v as usize])).collect::<Vec<_>>()
                    );
                    return Some((y, assump));
                }
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn build(us: &[Var], deps: &[(Var, &[Var])], cls: &[&[Lit]]) -> Formula {
        Formula::new(
            us.iter().chain(deps.iter().map(|(v, _)| v)).copied().max().unwrap_or(0),
            us.to_vec(),
            deps.iter().map(|&(e, d)| (e, d.iter().copied().collect())).collect(),
            cls.iter().map(|c| c.to_vec()).collect(),
        )
    }

    #[test]
    fn interpolant_buffer() {
        // ∀u ∃y(u): (¬u∨y)(u∨¬y)  ⟹  y ↔ u.
        let f = build(&[1], &[(2, &[1])], &[&[-1, 2], &[1, -2]]);
        let start = std::time::Instant::now();
        let defs = extract_interpolants(&f, &[2], 5.0, &start, false);
        let d = &defs[&2];
        assert_eq!(d.itp.inputs, vec![1]);
        // y ↔ u: at u=0 → y=0; u=1 → y=1.
        assert_eq!(d.itp.eval(d.root, 0b0), false);
        assert_eq!(d.itp.eval(d.root, 0b1), true);
    }

    #[test]
    fn interpolant_and() {
        // ∀u₁u₂ ∃y(u₁,u₂): y ↔ u₁∧u₂.
        let f = build(
            &[1, 2],
            &[(3, &[1, 2])],
            &[&[-1, -2, 3], &[1, -3], &[2, -3]],
        );
        let start = std::time::Instant::now();
        let defs = extract_interpolants(&f, &[3], 5.0, &start, false);
        let d = &defs[&3];
        // Find input order
        let i1 = d.itp.inputs.iter().position(|&v| v == 1).unwrap();
        let i2 = d.itp.inputs.iter().position(|&v| v == 2).unwrap();
        for u1 in 0..2u64 {
            for u2 in 0..2u64 {
                let a = (u1 << i1) | (u2 << i2);
                assert_eq!(
                    d.itp.eval(d.root, a),
                    u1 == 1 && u2 == 1,
                    "u1={} u2={}", u1, u2
                );
            }
        }
    }

    #[test]
    fn interpolant_xor() {
        // y ↔ u₁⊕u₂ (4 clauses).
        let f = build(
            &[1, 2],
            &[(3, &[1, 2])],
            &[&[-1, -2, -3], &[-1, 2, 3], &[1, -2, 3], &[1, 2, -3]],
        );
        let start = std::time::Instant::now();
        let defs = extract_interpolants(&f, &[3], 5.0, &start, false);
        let d = &defs[&3];
        let i1 = d.itp.inputs.iter().position(|&v| v == 1).unwrap();
        let i2 = d.itp.inputs.iter().position(|&v| v == 2).unwrap();
        for u1 in 0..2u64 {
            for u2 in 0..2u64 {
                let a = (u1 << i1) | (u2 << i2);
                assert_eq!(d.itp.eval(d.root, a), u1 != u2);
            }
        }
    }
}

    #[test]
    #[ignore]
    fn interpolant_validate_pec() {
        let path = "../../benchmarks/train/pec_circuits/miter/pec_alu_add_n4_k2_bb3_complete.dqdimacs.gz";
        let buf = String::from_utf8(
            std::process::Command::new("gzip").args(["-dc", path]).output().unwrap().stdout,
        ).unwrap();
        let f = crate::parse::parse(&buf).expect("parse");
        let start = std::time::Instant::now();
        let split = padoa_split(&f, 5.0, &start, false).expect("padoa");
        let defs = extract_interpolants(&f, &split.defined, 30.0, &start, false);
        assert!(validate_interpolants(&f, &defs, 20).is_none());
    }

    #[allow(dead_code)]
    fn _old_e179_debug() {
        let path = "../../benchmarks/train/pec_circuits/miter/pec_alu_add_n4_k2_bb3_complete.dqdimacs.gz";
        let buf = String::from_utf8(
            std::process::Command::new("gzip").args(["-dc", path]).output().unwrap().stdout,
        ).unwrap();
        let f = crate::parse::parse(&buf).expect("parse");
        let start = std::time::Instant::now();
        let split = padoa_split(&f, 5.0, &start, false).expect("padoa");
        let defs = extract_interpolants(&f, &split.defined, 30.0, &start, false);
        eprintln!("e179 in defined: {}", split.defined.contains(&179));
        eprintln!("e179 has interpolant: {}", defs.contains_key(&179));
        // Which z's would Padoa link for e179?
        let dy: BTreeSet<Var> = f.deps[&179].clone();
        let pad_linked: Vec<Var> = split.defined.iter().copied()
            .filter(|z| *z != 179 && f.deps[z].is_subset(&dy)).collect();
        eprintln!("Padoa would link {} z's for e179", pad_linked.len());
        // How many of those are in defs (interpolated before e179)?
        let itp_linked: Vec<Var> = pad_linked.iter().copied()
            .filter(|z| defs.contains_key(z)).collect();
        eprintln!("  of which {} are interpolated", itp_linked.len());
        // The non-interpolated linked z's:
        let missing: Vec<Var> = pad_linked.iter().copied()
            .filter(|z| !defs.contains_key(z)).collect();
        eprintln!("  missing: {:?}", &missing[..missing.len().min(10)]);
        // Manual: build the per-y CDCL with ALL pad_linked z's, see if UNSAT.
        let n = f.n_vars as Lit;
        let shift = |l: Lit| if l > 0 { l + n } else { l - n };
        let mut clauses: Vec<Clause> = Vec::new();
        for c in &f.clauses { clauses.push(c.clone()); }
        for c in &f.clauses { clauses.push(c.iter().map(|&l| shift(l)).collect()); }
        for &u in dy.iter().chain(pad_linked.iter()) {
            clauses.push(vec![-(u as Lit), shift(u as Lit)]);
            clauses.push(vec![u as Lit, -shift(u as Lit)]);
        }
        let mut cdcl = Cdcl::new(2*n as usize, &clauses);
        let mut model = vec![0i8; 2*n as usize +1];
        let unsat = !cdcl.solve(&[179, -shift(179)], &mut model, 100_000);
        eprintln!("with all pad_linked z's: unsat={} budget_hit={}", unsat, cdcl.budget_hit);
        // Dump e46's full proof + interpolant.
        std::env::set_var("FRUST_ITP_TRACE", "1");
        {
            let n = f.n_vars as Lit;
            let shift = |l: Lit| if l > 0 { l + n } else { l - n };
            let dy: BTreeSet<Var> = f.deps[&46].clone();
            let linked_z: Vec<Var> = vec![40, 43, 44]; // from observed inputs
            let mut clauses: Vec<Clause> = Vec::new();
            for c in &f.clauses { clauses.push(c.clone()); }
            for c in &f.clauses { clauses.push(c.iter().map(|&l| shift(l)).collect()); }
            for &u in dy.iter().chain(linked_z.iter()) {
                clauses.push(vec![-(u as Lit), shift(u as Lit)]);
                clauses.push(vec![u as Lit, -shift(u as Lit)]);
            }
            let mut cdcl = Cdcl::new(2*n as usize, &clauses);
            cdcl.enable_proof_log();
            let mut model = vec![0i8; 2*n as usize +1];
            let unsat = !cdcl.solve(&[46, -shift(46)], &mut model, 100_000);
            eprintln!("e46 proof: unsat={}", unsat);
            let pl = cdcl.proof.as_ref().unwrap();
            eprintln!("  final_clause={:?}", pl.final_clause);
            eprintln!("  final_chain.len={}", pl.final_chain.len());
            for &(cr, piv) in &pl.final_chain {
                let lits = cdcl.clause_lits(cr);
                let learned = pl.ante.contains_key(&cr);
                eprintln!("    cr={} piv={} lits={:?} learned={}", cr, piv, lits, learned);
            }
            // Now run mcmillan with trace.
            let nu = n as Var;
            let shared: HashSet<Var> = dy.iter().chain(linked_z.iter()).copied().collect();
            let side = |cr: u32| if cdcl.clause_lits(cr).iter().all(|&l| var(l) <= nu) {
                crate::interpolant::Side::A
            } else {
                crate::interpolant::Side::B
            };
            let a_local = |v: Var| v <= nu && !shared.contains(&v);
            let (itp, root) = mcmillan(&cdcl, side, &shared, a_local).unwrap();
            eprintln!("e46 interpolant: inputs={:?} gates={:?} root={}", itp.inputs, itp.gates, root);
        }
        std::env::remove_var("FRUST_ITP_TRACE");
        // Validate all interpolants
        let bad = validate_interpolants(&f, &defs, 20);
        match bad {
            None => eprintln!("all interpolants validate at 20 random rows"),
            Some((y, row)) => {
                eprintln!("MISMATCH: y={} at row {:?}", y, &row[..row.len().min(8)]);
                let d = &defs[&y];
                eprintln!("  inputs={:?} gates={} root={}", d.itp.inputs, d.itp.gates.len(), d.root);
                for (i, g) in d.itp.gates.iter().enumerate() {
                    eprintln!("  g{}: {:?}", i, g);
                }
            }
        }
    }

    #[test]
    #[ignore]  // bench-scale; run with --ignored
    fn interpolant_pec_sample() {
        let path = "../../benchmarks/train/pec_circuits/miter/pec_alu_add_n4_k2_bb3_complete.dqdimacs.gz";
        let buf = String::from_utf8(
            std::process::Command::new("gzip").args(["-dc", path]).output().unwrap().stdout,
        ).unwrap();
        let f = crate::parse::parse(&buf).expect("parse");
        let start = std::time::Instant::now();
        let split = padoa_split(&f, 5.0, &start, false).expect("padoa");
        eprintln!("padoa: {} defined, {} undef ({:.2}s)", split.defined.len(), split.undefined.len(), start.elapsed().as_secs_f64());
        let t1 = std::time::Instant::now();
        let defs = extract_interpolants(&f, &split.defined, 30.0, &start, true);
        let mut sizes: Vec<usize> = defs.values().map(|d| d.itp.gates.len()).collect();
        sizes.sort_unstable();
        eprintln!("interpolants: {}/{} in {:.2}s; gate sizes min/med/max = {}/{}/{}",
            defs.len(), split.defined.len(), t1.elapsed().as_secs_f64(),
            sizes.first().copied().unwrap_or(0),
            sizes.get(sizes.len()/2).copied().unwrap_or(0),
            sizes.last().copied().unwrap_or(0));
    }
