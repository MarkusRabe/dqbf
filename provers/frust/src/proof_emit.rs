//! Convert a CDCL `ProofLog` (resolution chains) into a fork-resolution
//! `.frp`. CDCL's chain *is* Q-resolution: assumptions sit at decision
//! level 0 and never become 1-UIP pivots, so every pivot in the chain
//! is a non-assumption variable. The chain ends in an assumption-only
//! clause; when those assumptions are universals, ∀-reduce → ⊥.
//!
//! Reference: `scripts/unsat_cert_mapping.py` for the worked examples
//! each path maps to.

use crate::cdcl::Cdcl;
use crate::formula::{var, Formula, Lit};
use crate::proof::{Proof, Step};
use std::collections::{BTreeSet, HashMap};

fn resolve(a: &BTreeSet<Lit>, b: &[Lit], pivot: u32) -> Option<BTreeSet<Lit>> {
    let p = pivot as Lit;
    let mut out: BTreeSet<Lit> = a.iter().copied().filter(|&l| var(l) != pivot).collect();
    for &l in b {
        if var(l) == pivot {
            continue;
        }
        if out.contains(&-l) {
            return None; // tautology — chain replays propositionally,
                         // so this only fires if the seed itself is one.
        }
        out.insert(l);
    }
    let _ = p;
    Some(out)
}

/// Re-prove `f.clauses ∧ row` UNSAT with a fresh proof-logging CDCL,
/// then convert the chain to `.frp`. Universals are non-decision so
/// every CDCL pivot is existential. Returns `None` only if the row is
/// somehow not UNSAT under the original matrix (e.g., the original
/// witness depended on a saturate-cross-feed clause).
pub fn reprove_row_unsat(
    f: &Formula,
    row: &[Lit],
    max_steps: usize,
    deadline: f64,
    start: &std::time::Instant,
) -> Option<Proof> {
    let mut cdcl = Cdcl::new(f.n_vars as usize, &f.clauses);
    cdcl.enable_proof_log();
    for &u in &f.universals {
        cdcl.set_decision(u, false);
    }
    let mut model = vec![0i8; f.n_vars as usize + 1];
    // The verdict is already known; reprove is best-effort cert recovery.
    // A 50 k-conflict refutation can still emit >>50 k res steps and
    // (with proof-log bookkeeping) take seconds — under j=48 contention
    // that turns 60 ms verdicts into 10 s timeouts. Cap at the deadline.
    let mut spent = 0u64;
    loop {
        if !cdcl.solve(row, &mut model, 5_000) {
            break;
        }
        spent += 5_000;
        if cdcl.budget_hit && start.elapsed().as_secs_f64() < deadline && spent < 50_000 {
            continue;
        }
        return None;
    }
    if start.elapsed().as_secs_f64() >= deadline {
        return None;
    }
    let mut p = cdcl_row_unsat_to_frp(f, &cdcl, max_steps)?;
    p.compact();
    Some(p)
}

/// Emit a `.frp` for a CDCL refutation under universal-only assumptions.
/// Returns `None` if the chain references a clause we can't justify
/// (e.g., an `add_external` clause without an `ante` entry, or a pivot
/// that turns out to be universal because not every universal was
/// assumed in partial-scan mode).
pub fn cdcl_row_unsat_to_frp(f: &Formula, cdcl: &Cdcl, max_steps: usize) -> Option<Proof> {
    let pl = cdcl.proof.as_ref()?;
    if pl.final_chain.is_empty() {
        return None;
    }
    // Every lit in the final clause must be universal so ∀-reduce → ⊥.
    if pl.final_clause.iter().any(|&l| !f.is_universal(var(l))) {
        return None;
    }
    let univ: BTreeSet<u32> = f.universals.iter().copied().collect();

    // 1. Collect all crefs reachable from final_chain via ante.
    let mut order: Vec<u32> = Vec::new();
    let mut state: HashMap<u32, u8> = HashMap::new(); // 0 absent / 1 visiting / 2 done
    let mut stack: Vec<(u32, usize)> = Vec::new();
    let push_roots = |st: &mut Vec<(u32, usize)>, ch: &[(u32, u32)]| {
        for &(cr, _) in ch {
            st.push((cr, 0));
        }
    };
    push_roots(&mut stack, &pl.final_chain);
    while let Some((cr, i)) = stack.pop() {
        match state.get(&cr).copied().unwrap_or(0) {
            2 => continue,
            1 if i == 0 => continue,
            _ => {}
        }
        let ante = pl.ante.get(&cr);
        match ante {
            None => {
                // Input clause or external. Check it's an axiom.
                // (Axiom check happens at emit time against f.clauses.)
                state.insert(cr, 2);
                order.push(cr);
            }
            Some(ch) => {
                if i == 0 {
                    state.insert(cr, 1);
                    stack.push((cr, 1));
                    for &(dep, _) in ch {
                        if state.get(&dep).copied().unwrap_or(0) == 0 {
                            stack.push((dep, 0));
                        }
                    }
                } else {
                    state.insert(cr, 2);
                    order.push(cr);
                }
            }
        }
    }

    // 2. Emit. step_of[cr] = .frp index of the step deriving cr's clause.
    let mut proof = Proof::default();
    let mut step_of: HashMap<u32, usize> = HashMap::new();
    let f_clauses: std::collections::HashSet<BTreeSet<Lit>> = f
        .clauses
        .iter()
        .map(|c| c.iter().copied().collect())
        .collect();

    // Chain replay resolves against the *derived* clause for each cref
    // (which for learned clauses is what its own chain produced), not
    // the raw arena lits. The two coincide once chains are correct;
    // until then this isolates one bad chain instead of cascading.
    let emit_chain = |proof: &mut Proof,
                      step_of: &HashMap<u32, usize>,
                      derived_of: &HashMap<u32, BTreeSet<Lit>>,
                      chain: &[(u32, u32)],
                      cap: usize|
     -> Option<(usize, BTreeSet<Lit>)> {
        let (seed, _) = chain[0];
        let mut acc: BTreeSet<Lit> = derived_of.get(&seed)?.clone();
        let mut idx = *step_of.get(&seed)?;
        for &(cr, pivot) in &chain[1..] {
            if univ.contains(&pivot) || proof.steps.len() > cap {
                return None;
            }
            let other = *step_of.get(&cr)?;
            let other_lits: Vec<Lit> = derived_of.get(&cr)?.iter().copied().collect();
            acc = resolve(&acc, &other_lits, pivot)?;
            idx = proof.add(Step::res(
                &acc.iter().copied().collect(),
                idx,
                other,
                pivot,
            ));
        }
        Some((idx, acc))
    };

    let mut derived_of: HashMap<u32, BTreeSet<Lit>> = HashMap::new();
    for &cr in &order {
        if let Some(ch) = pl.ante.get(&cr) {
            let (idx, acc) = emit_chain(&mut proof, &step_of, &derived_of, ch, max_steps)?;
            let stored: BTreeSet<Lit> = cdcl.clause_lits(cr).into_iter().collect();
            if acc != stored {
                // Chain replay should reproduce the learned clause
                // exactly once level-0 lits are resolved in reverse-
                // trail order. Any drift means the recording is buggy;
                // don't emit a wrong proof.
                return None;
            }
            step_of.insert(cr, idx);
            derived_of.insert(cr, acc);
        } else {
            let lits: BTreeSet<Lit> = cdcl.clause_lits(cr).into_iter().collect();
            if !f_clauses.contains(&lits) {
                // External (saturate cross-feed) — can't justify.
                return None;
            }
            let idx = proof.add(Step::axiom(&lits.iter().copied().collect()));
            step_of.insert(cr, idx);
            derived_of.insert(cr, lits);
        }
    }
    let (last, acc) = emit_chain(&mut proof, &step_of, &derived_of, &pl.final_chain, max_steps)?;
    // 3. ∀-reduce to ⊥. The verifier allows ∀-reduce inline with `res`,
    // so the last `res` could already be ⊥ — but emit an explicit `ured`
    // for clarity when acc isn't already empty.
    if !acc.is_empty() {
        proof.add(Step::ured(&vec![], last));
    }
    Some(proof)
}
