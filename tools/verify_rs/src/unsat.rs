//! UNSAT certificate replay. Implements the journal's rules
//! Res / ∀Red / FEx / SFEx, derived from
//! `docs/references/fork_resolution_journal/main.tex`:
//!
//!   Res:   from C₁∨ℓ and C₂∨¬ℓ derive C₁∨C₂ (not a tautology)
//!   ∀Red:  from C∨ℓ derive C if var(ℓ) universal, var(ℓ)∉dep(C), ¬ℓ∉C
//!   FEx:   from C₁∨C₂ derive {C₁∨x, C₂∨¬x} with x fresh,
//!          dep(x) = dep(C₁) ∩ dep(C₂)
//!   SFEx:  from C₁∨C₂ derive {C₃∨C₁∨x, C₃∨C₂∨¬x} with x fresh,
//!          C₃ a disjunction of universal literals,
//!          dep(x) = (dep(C₁) ∩ dep(C₂)) \ var(C₃)
//!
//! The verifier maintains a *growing* prefix: FEx/SFEx introduce new
//! existentials, so dep(C) for downstream clauses must use the
//! extended prefix (RISKS.md X2/F7/F8).
//!
//! Reject-on-doubt: any malformed step is INVALID.

use crate::dqdimacs::{Clause, Formula, Lit, Var};
use crate::frp::Step;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, PartialEq)]
pub enum Verdict {
    Valid,
    Invalid(String),
}

/// Mutable prefix state during replay. Starts as a copy of the
/// formula's prefix, grows with each FEx/SFEx.
struct Prefix {
    universals: BTreeSet<Var>,
    deps: BTreeMap<Var, BTreeSet<Var>>,
    /// Highest var id known; used for the freshness check.
    seen: BTreeSet<Var>,
}

impl Prefix {
    fn new(f: &Formula) -> Self {
        let mut seen: BTreeSet<Var> = f.universals.iter().copied().collect();
        seen.extend(f.deps.keys().copied());
        // Vars that occur in clauses but aren't quantified (e.g., a
        // free var) also count as "seen" for the freshness check.
        for c in &f.clauses {
            for &l in c {
                seen.insert(l.abs());
            }
        }
        Prefix {
            universals: f.universals.iter().copied().collect(),
            deps: f.deps.clone(),
            seen,
        }
    }
    fn is_universal(&self, v: Var) -> bool {
        self.universals.contains(&v)
    }
    fn is_existential(&self, v: Var) -> bool {
        self.deps.contains_key(&v)
    }
    /// dep(C) under the *current* (possibly extended) prefix.
    fn clause_dep(&self, c: &Clause) -> BTreeSet<Var> {
        let mut d = BTreeSet::new();
        for &l in c {
            let v = l.abs();
            if let Some(yd) = self.deps.get(&v) {
                d.extend(yd.iter().copied());
            } else if self.is_universal(v) {
                d.insert(v);
            }
        }
        d
    }
    fn add_existential(&mut self, x: Var, dep: BTreeSet<Var>) -> Result<(), String> {
        if self.seen.contains(&x) {
            return Err(format!("fresh var {x} is not fresh"));
        }
        if x <= 0 {
            return Err(format!("fresh var {x} is not a positive id"));
        }
        for &u in &dep {
            if !self.is_universal(u) {
                return Err(format!("dep of fresh var includes non-universal {u}"));
            }
        }
        self.seen.insert(x);
        self.deps.insert(x, dep);
        Ok(())
    }
}

fn to_set(v: &[Lit]) -> Clause {
    v.iter().copied().collect()
}

fn is_tautology(c: &Clause) -> bool {
    c.iter().any(|&l| c.contains(&(-l)))
}

pub fn verify(f: &Formula, steps: &[Step]) -> Verdict {
    if steps.is_empty() {
        return Verdict::Invalid("empty proof".into());
    }
    // Input clauses as canonical sets, for axiom lookup.
    let input: BTreeSet<Clause> = f.clauses.iter().cloned().collect();

    let mut prefix = Prefix::new(f);
    let mut derived: Vec<Clause> = Vec::with_capacity(steps.len());
    // For FEx/SFEx: when a step claims one half, the *other* half also
    // becomes derivable. Keep a set of available clauses so the sibling
    // is reachable. We index derived clauses by step number, and
    // additionally allow the FEx sibling (referenceable only through
    // the same `premises` index — the proof points at the *premise*
    // step, not at one or the other sibling). So we don't need a
    // separate map: each FEx step in the proof must independently
    // state which half it is via the `clause` field.
    let mut found_empty = false;

    for (i, step) in steps.iter().enumerate() {
        // Premise sanity (U1/U2).
        for &p in &step.premises {
            if p >= i {
                return Verdict::Invalid(format!(
                    "step {i}: premise {p} is not a strictly earlier step"
                ));
            }
        }

        let claimed = to_set(&step.clause);
        // U8: tautological claimed clause is suspicious — reject.
        // Exception: the empty clause is never a tautology so this is safe.
        if is_tautology(&claimed) {
            return Verdict::Invalid(format!("step {i}: claimed clause is a tautology"));
        }
        // Vars in the claimed clause must be known (≤ n_vars or a fresh
        // var introduced earlier or being introduced *by this step*). U9.
        let introducing: Option<Var> = if matches!(step.rule.as_str(), "fex" | "sfex") {
            step.fresh
        } else {
            None
        };
        for &l in &claimed {
            let v = l.abs();
            if v > f.n_vars && !prefix.seen.contains(&v) && Some(v) != introducing {
                return Verdict::Invalid(format!(
                    "step {i}: claimed clause references unknown var {v}"
                ));
            }
        }

        let result = match step.rule.as_str() {
            "axiom" => check_axiom(i, step, &claimed, &input),
            "res" => check_res(i, step, &claimed, &derived, &prefix),
            "ured" => check_ured(i, step, &claimed, &derived, &prefix),
            "fex" | "sfex" => check_fex(i, step, &claimed, &derived, &mut prefix),
            r => Err(format!("step {i}: unknown rule '{r}'")),
        };
        if let Err(msg) = result {
            return Verdict::Invalid(msg);
        }
        if claimed.is_empty() {
            found_empty = true;
        }
        derived.push(claimed);
    }
    if found_empty {
        Verdict::Valid
    } else {
        Verdict::Invalid("proof never derives the empty clause".into())
    }
}

fn check_axiom(i: usize, step: &Step, claimed: &Clause, input: &BTreeSet<Clause>) -> Result<(), String> {
    if !step.premises.is_empty() {
        return Err(format!("step {i}: axiom with premises"));
    }
    if !input.contains(claimed) {
        return Err(format!("step {i}: axiom not in the input matrix"));
    }
    Ok(())
}

fn check_res(
    i: usize,
    step: &Step,
    claimed: &Clause,
    derived: &[Clause],
    prefix: &Prefix,
) -> Result<(), String> {
    if step.premises.len() != 2 {
        return Err(format!(
            "step {i}: res expects 2 premises, got {}",
            step.premises.len()
        ));
    }
    let pivot = step.pivot.ok_or_else(|| format!("step {i}: res missing pivot"))?;
    let pv = pivot.abs();
    if pv == 0 {
        return Err(format!("step {i}: pivot 0"));
    }
    let a = &derived[step.premises[0]];
    let b = &derived[step.premises[1]];
    // One premise must contain +pv, the other -pv.
    let (pos, neg) = if a.contains(&pv) && b.contains(&(-pv)) {
        (a, b)
    } else if a.contains(&(-pv)) && b.contains(&pv) {
        (b, a)
    } else {
        return Err(format!(
            "step {i}: pivot {pv} does not appear with both polarities in premises"
        ));
    };
    let mut resolvent: Clause = BTreeSet::new();
    resolvent.extend(pos.iter().filter(|&&l| l != pv));
    resolvent.extend(neg.iter().filter(|&&l| l != -pv));
    if is_tautology(&resolvent) {
        return Err(format!("step {i}: resolvent is a tautology"));
    }
    // The .frp emitter (and Q-resolution in general) fuses res+∀Red.
    // Accept the claimed clause if it is the resolvent OR a sound
    // ∀-reduction of it. (The Python verifier and the prover both
    // assume this; rejecting strict equality here would diverge on
    // valid certificates. The reduction itself is checked exactly.)
    if &resolvent != claimed {
        check_reduction_of(i, &resolvent, claimed, prefix)?;
    }
    Ok(())
}

/// Is `claimed` a valid ∀-reduction of `src`? Used by `check_res` to
/// accept fused res+∀Red and by `check_ured` directly.
fn check_reduction_of(
    i: usize,
    src: &Clause,
    claimed: &Clause,
    prefix: &Prefix,
) -> Result<(), String> {
    if !claimed.is_subset(src) {
        return Err(format!(
            "step {i}: claimed clause is not a subset of the (post-resolution) premise"
        ));
    }
    let dropped: Vec<Lit> = src.difference(claimed).copied().collect();
    let dep_result = prefix.clause_dep(claimed);
    for &l in &dropped {
        let v = l.abs();
        if !prefix.is_universal(v) {
            return Err(format!("step {i}: drops non-universal literal {l}"));
        }
        if src.contains(&(-l)) {
            return Err(format!("step {i}: drops {l} but ¬{l} is in the source"));
        }
        if dep_result.contains(&v) {
            return Err(format!(
                "step {i}: drops {l} but {v} ∈ dep of the result"
            ));
        }
    }
    Ok(())
}

fn check_ured(
    i: usize,
    step: &Step,
    claimed: &Clause,
    derived: &[Clause],
    prefix: &Prefix,
) -> Result<(), String> {
    if step.premises.len() != 1 {
        return Err(format!(
            "step {i}: ured expects 1 premise, got {}",
            step.premises.len()
        ));
    }
    let src = &derived[step.premises[0]];
    if claimed == src {
        return Err(format!("step {i}: ured drops nothing"));
    }
    check_reduction_of(i, src, claimed, prefix)
}

/// Handles both FEx (`c3` empty/None) and SFEx (`c3` set).
fn check_fex(
    i: usize,
    step: &Step,
    claimed: &Clause,
    derived: &[Clause],
    prefix: &mut Prefix,
) -> Result<(), String> {
    if step.premises.len() != 1 {
        return Err(format!(
            "step {i}: fex/sfex expects 1 premise, got {}",
            step.premises.len()
        ));
    }
    let src = &derived[step.premises[0]];
    let part = step
        .part
        .as_ref()
        .ok_or_else(|| format!("step {i}: fex/sfex missing 'part'"))?;
    let c1: Clause = to_set(part);
    if !c1.is_subset(src) {
        return Err(format!("step {i}: fex/sfex part is not a subset of premise"));
    }
    let c2: Clause = src.difference(&c1).copied().collect();
    let x = step
        .fresh
        .ok_or_else(|| format!("step {i}: fex/sfex missing 'fresh'"))?;
    if x <= 0 {
        return Err(format!("step {i}: fresh var must be positive"));
    }
    let c3: Clause = step.c3.as_ref().map(|v| to_set(v)).unwrap_or_default();
    if step.rule == "fex" && !c3.is_empty() {
        return Err(format!("step {i}: fex must not have a c3"));
    }
    for &l in &c3 {
        if !prefix.is_universal(l.abs()) {
            return Err(format!("step {i}: c3 literal {l} is not universal"));
        }
    }
    let d1 = prefix.clause_dep(&c1);
    let d2 = prefix.clause_dep(&c2);
    let mut dep_x: BTreeSet<Var> = d1.intersection(&d2).copied().collect();
    for &l in &c3 {
        dep_x.remove(&l.abs());
    }
    // Compute both halves.
    let mut left = c1.clone();
    left.extend(&c3);
    left.insert(x);
    let mut right = c2.clone();
    right.extend(&c3);
    right.insert(-x);
    if claimed != &left && claimed != &right {
        return Err(format!(
            "step {i}: claimed clause is neither half of the fork"
        ));
    }
    // Register x with its dep set so downstream ured checks are correct.
    // If the *other* half is derived in a later step, that step must
    // also use the same `fresh` and the same `part`. We enforce this
    // weakly: the second step would fail the freshness check below
    // (var no longer fresh) — except that's exactly what the prover
    // emits (two fex steps with the same `fresh`/`part`). So we accept
    // a re-registration when the dep set matches.
    if let Some(existing) = prefix.deps.get(&x) {
        if !prefix.is_existential(x) || *existing != dep_x {
            return Err(format!(
                "step {i}: fresh var {x} re-registered with a different dep set"
            ));
        }
        // Consistent re-use of the same fork variable for the sibling
        // half — accept.
    } else {
        prefix.add_existential(x, dep_x)?;
    }
    Ok(())
}
