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

/// Re-prove `f.clauses ∧ forcings ∧ row` UNSAT and emit a `.frp`.
///
/// **Forcing-chain stitching (iter101)**: a CEGAR-derived UNSAT row may
/// only refute under the live forcing clauses — `f.clauses ∧ row` is
/// SAT but `f.clauses ∧ forcings ∧ row` is not. Each forcing clause
/// `¬ante ∨ ℓ_y` (where `ante` are universals and `ℓ_y` is an
/// existential literal) is itself a Q-resolution-derivable clause:
/// re-prove `f.clauses ∧ ante ∧ ¬ℓ_y → ⊥` and replay the chain. The
/// final clause of that sub-chain subsumes the forcing clause, and the
/// row refutation references it as a derived axiom rather than a raw
/// matrix clause.
///
/// Forcings are re-derived in *learn order*: a later forcing may have
/// been proved using earlier ones (CEGAR feeds them back into
/// `consist`). Each pass adds the previously-derived ones as axioms so
/// chained forcings re-derive on a later pass; bounded to
/// `MAX_FORCING_PASSES` so a pathological dependency loop bails.
pub fn reprove_row_unsat(
    f: &Formula,
    row: &[Lit],
    forcings: &[Vec<Lit>],
    max_steps: usize,
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
) -> Option<Proof> {
    let n_inst = f.clauses.len();
    let mut proof = Proof::default();
    // Extra axioms passed to chain conversion: clause-set → step index.
    let mut extra_axioms: HashMap<BTreeSet<Lit>, usize> = HashMap::new();
    // Axiom set the per-forcing sub-prove CDCL is allowed to use.
    let mut derived_clauses: Vec<Vec<Lit>> = Vec::new();
    // Forcings that haven't re-derived yet, indexed for retry.
    let mut pending: Vec<usize> = (0..forcings.len()).collect();

    const MAX_FORCING_PASSES: usize = 4;
    for _pass in 0..MAX_FORCING_PASSES {
        if pending.is_empty() {
            break;
        }
        if start.elapsed().as_secs_f64() >= deadline {
            if debug {
                eprintln!("c [reprove] deadline before forcing pass {}", _pass);
            }
            return None;
        }
        let mut still_pending: Vec<usize> = Vec::new();
        for &i in &pending {
            // Negate the forcing/constraint clause: assume ¬each lit.
            let assume: Vec<Lit> = forcings[i].iter().map(|&l| -l).collect();
            // Skip duplicates (CEGAR can learn the same clause twice
            // across rounds, partner cells often share a constraint).
            let fc_set: BTreeSet<Lit> = forcings[i].iter().copied().collect();
            if extra_axioms.contains_key(&fc_set) {
                continue;
            }
            // Build a CDCL with f.clauses + already-derived forcings.
            let mut all_clauses: Vec<Vec<Lit>> = f.clauses.clone();
            all_clauses.extend(derived_clauses.iter().cloned());
            let mut sub = Cdcl::new(f.n_vars as usize, &all_clauses);
            sub.enable_proof_log();
            for &u in &f.universals {
                sub.set_decision(u, false);
            }
            let mut model = vec![0i8; f.n_vars as usize + 1];
            let sat = sub.solve(&assume, &mut model, 50_000);
            if sub.budget_hit || sat {
                // Couldn't re-derive this forcing yet (or budget). Retry
                // next pass once more forcings are available as axioms.
                still_pending.push(i);
                continue;
            }
            // Convert the sub-chain. The final clause is over the
            // assumptions (ante ∪ ¬then negated → ¬ante ∪ then), not
            // universals-only — pass the relaxed flavour.
            match cdcl_chain_to_frp_into(
                f,
                &sub,
                &derived_clauses[..],
                n_inst,
                &extra_axioms,
                &mut proof,
                max_steps,
                false, // no ured-to-bottom
                debug,
            ) {
                Some((idx, derived)) => {
                    // `derived` may strictly subsume the forcing clause;
                    // record it so the row refutation uses the actual
                    // chain output, and downstream sub-proves see it.
                    derived_clauses.push(derived.iter().copied().collect());
                    extra_axioms.insert(derived, idx);
                }
                None => {
                    still_pending.push(i);
                }
            }
        }
        if still_pending.len() == pending.len() {
            // No progress this pass; stop.
            pending = still_pending;
            break;
        }
        pending = still_pending;
    }
    if !pending.is_empty() {
        if debug {
            eprintln!(
                "c [reprove] {} of {} forcings could not re-derive",
                pending.len(),
                forcings.len()
            );
        }
        // Best-effort: try the row refutation anyway with the forcings
        // we did derive — it may not need the rest.
    }

    // ---- Row refutation with f.clauses ∪ derived forcings ----
    let mut all_clauses: Vec<Vec<Lit>> = f.clauses.clone();
    all_clauses.extend(derived_clauses.iter().cloned());
    let mut cdcl = Cdcl::new(f.n_vars as usize, &all_clauses);
    cdcl.enable_proof_log();
    for &u in &f.universals {
        cdcl.set_decision(u, false);
    }
    let mut model = vec![0i8; f.n_vars as usize + 1];
    // Chunk the conflict budget so we can bail at the wall-clock deadline.
    loop {
        let sat = cdcl.solve(row, &mut model, 5_000);
        if !cdcl.budget_hit {
            if sat {
                if debug {
                    eprintln!(
                        "c [reprove] row SAT under f.clauses ∪ {} forcings",
                        derived_clauses.len()
                    );
                }
                return None;
            }
            break;
        }
        if start.elapsed().as_secs_f64() >= deadline {
            if debug {
                eprintln!("c [reprove] deadline {:.2}s", deadline);
            }
            return None;
        }
    }
    cdcl_chain_to_frp_into(
        f,
        &cdcl,
        &derived_clauses[..],
        n_inst,
        &extra_axioms,
        &mut proof,
        max_steps,
        true, // emit final ured to ⊥
        debug,
    )?;
    if start.elapsed().as_secs_f64() >= deadline {
        if debug {
            eprintln!("c [reprove] deadline after convert");
        }
        return None;
    }
    proof.compact();
    Some(proof)
}

/// Emit a `.frp` for a CDCL refutation under universal-only assumptions.
/// Returns `None` if the chain references a clause we can't justify
/// (e.g., an `add_external` clause without an `ante` entry).
pub fn cdcl_row_unsat_to_frp(f: &Formula, cdcl: &Cdcl, max_steps: usize) -> Option<Proof> {
    let mut p = Proof::default();
    cdcl_chain_to_frp_into(f, cdcl, &[], f.clauses.len(), &HashMap::new(), &mut p, max_steps, true, false)?;
    Some(p)
}

/// Append a CDCL refutation chain to `proof`. The CDCL was built with
/// `f.clauses` followed by `derived_clauses`; non-`f.clauses` axiom
/// crefs must match a `derived_clauses` entry whose `.frp` step index is
/// in `extra_axioms`. Returns `(final_step_idx, final_clause_set)`.
///
/// When `to_bottom` is set, the final clause must be universal-only and
/// a `ured`-to-⊥ step is appended; otherwise the final clause is left
/// as derived (used for re-deriving a forcing clause).
#[allow(clippy::too_many_arguments)]
pub fn cdcl_chain_to_frp_into(
    f: &Formula,
    cdcl: &Cdcl,
    derived_clauses: &[Vec<Lit>],
    n_inst: usize,
    extra_axioms: &HashMap<BTreeSet<Lit>, usize>,
    proof: &mut Proof,
    max_steps: usize,
    to_bottom: bool,
    debug: bool,
) -> Option<(usize, BTreeSet<Lit>)> {
    let _ = (derived_clauses, n_inst);
    macro_rules! bail {
        ($($a:tt)*) => {{
            if debug { eprintln!("c [reprove-frp] {}", format!($($a)*)); }
            return None;
        }};
    }
    let pl = cdcl.proof.as_ref()?;
    if pl.final_chain.is_empty() {
        bail!("empty final_chain");
    }
    // For a row refutation the final clause must be universal so it
    // ∀-reduces to ⊥. For a forcing re-derivation the final clause has
    // an existential lit; the caller doesn't append `ured`.
    if to_bottom && pl.final_clause.iter().any(|&l| !f.is_universal(var(l))) {
        bail!(
            "final_clause has non-universal lit: {:?}",
            pl.final_clause
                .iter()
                .filter(|&&l| !f.is_universal(var(l)))
                .take(3)
                .collect::<Vec<_>>()
        );
    }

    // 1. Collect all crefs reachable from final_chain via ante.
    let mut order: Vec<u32> = Vec::new();
    let mut state: HashMap<u32, u8> = HashMap::new(); // 0 absent / 1 visiting / 2 done
    let mut stack: Vec<(u32, usize)> = Vec::new();
    for &(cr, _) in &pl.final_chain {
        stack.push((cr, 0));
    }
    while let Some((cr, i)) = stack.pop() {
        match state.get(&cr).copied().unwrap_or(0) {
            2 => continue,
            1 if i == 0 => continue,
            _ => {}
        }
        let ante = pl.ante.get(&cr);
        match ante {
            None => {
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
    let mut step_of: HashMap<u32, usize> = HashMap::new();
    let f_clauses: std::collections::HashSet<BTreeSet<Lit>> = f
        .clauses
        .iter()
        .map(|c| c.iter().copied().collect())
        .collect();

    // Chain replay resolves against the *derived* clause for each cref
    // (which for learned clauses is what its own chain produced), not
    // the raw arena lits.
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
            // QU-resolution: universal pivots are allowed (the journal
            // paper §soundness defers to QU-resolution for DQBF).
            if proof.steps.len() > cap {
                if debug {
                    eprintln!("c [reprove-frp]   cap {}", cap);
                }
                return None;
            }
            let other = match step_of.get(&cr) {
                Some(&v) => v,
                None => {
                    if debug {
                        eprintln!("c [reprove-frp]   missing step for cr={}", cr);
                    }
                    return None;
                }
            };
            let other_lits: Vec<Lit> = derived_of.get(&cr)?.iter().copied().collect();
            acc = match resolve(&acc, &other_lits, pivot) {
                Some(a) => a,
                None => {
                    if debug {
                        eprintln!("c [reprove-frp]   tautology at pivot {}", pivot);
                    }
                    return None;
                }
            };
            idx = proof.add(Step::res(&acc.iter().copied().collect(), idx, other, pivot));
        }
        Some((idx, acc))
    };

    let mut derived_of: HashMap<u32, BTreeSet<Lit>> = HashMap::new();
    for &cr in &order {
        if let Some(ch) = pl.ante.get(&cr) {
            let r = emit_chain(proof, &step_of, &derived_of, ch, max_steps);
            let (idx, acc) = match r {
                Some(v) => v,
                None => bail!(
                    "chain emit failed at cr={} (cap {} or missing dep)",
                    cr,
                    max_steps
                ),
            };
            let stored: BTreeSet<Lit> = cdcl.clause_lits(cr).into_iter().collect();
            if acc != stored {
                bail!(
                    "chain replay drift cr={}: replay={} stored={}",
                    cr,
                    acc.len(),
                    stored.len()
                );
            }
            step_of.insert(cr, idx);
            derived_of.insert(cr, acc);
        } else {
            let lits: BTreeSet<Lit> = cdcl.clause_lits(cr).into_iter().collect();
            if let Some(&ax_idx) = extra_axioms.get(&lits) {
                // Pre-derived forcing clause: reference its existing
                // `.frp` step rather than re-emitting an axiom.
                step_of.insert(cr, ax_idx);
                derived_of.insert(cr, lits);
            } else if f_clauses.contains(&lits) {
                let idx = proof.add(Step::axiom(&lits.iter().copied().collect()));
                step_of.insert(cr, idx);
                derived_of.insert(cr, lits);
            } else {
                // External (saturate cross-feed or unreachable forcing).
                bail!("axiom cr={} not in f.clauses ∪ forcings (|c|={})", cr, lits.len());
            }
        }
    }
    let r = emit_chain(proof, &step_of, &derived_of, &pl.final_chain, max_steps);
    let (last, acc) = match r {
        Some(v) => v,
        None => bail!("final_chain emit failed"),
    };
    if to_bottom {
        // ∀-reduce to ⊥. The verifier allows ∀-reduce inline with `res`,
        // so the last `res` could already be ⊥ — but emit an explicit
        // `ured` for clarity when acc isn't already empty.
        if !acc.is_empty() {
            proof.add(Step::ured(&vec![], last));
        }
    }
    Some((last, acc))
}
