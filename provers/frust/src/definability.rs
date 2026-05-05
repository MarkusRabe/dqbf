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
use std::collections::{BTreeSet, HashMap, HashSet};

pub struct DefSplit {
    pub defined: Vec<Var>,
    pub undefined: Vec<Var>,
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
