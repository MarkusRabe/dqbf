//! Definability-guided SAT proof via validity-CEGAR (Pedant-style).
//!
//! Three cooperating CDCL instances:
//!   - `consist`  : matrix(U, E) — gives the satisfying E for a row.
//!   - `validity` : Tseitin(¬matrix) ∧ forcing-clauses ∧ arbiter-links —
//!                  UNSAT here ⇒ ∀U the encoded Skolem satisfies matrix.
//!   - `arbsolve` : clauses over arbiter vars only — searches the (small)
//!                  space of choices for non-uniquely-defined existentials.
//!
//! Loop: pick arbiter assignment → ask validity for a counterexample U*
//!       → ask consist for the row model → for each disagreeing y,
//!       either learn a forcing clause (defined y, core ⊆ dep(y)) or
//!       allocate an arbiter cell (undefined y). If consist is UNSAT
//!       under U*+arbiters, learn an arbiter conflict clause and re-pick.
//!
//! Reference: Reichl/Slivovsky/Szeider, "Pedant" (SAT'21);
//! Rabe/Tentrup, "CAQE" (FMCAD'15) for clausal-abstraction CEGAR.

use crate::aiger::Skolem;
use crate::cdcl::Cdcl;
use crate::formula::{var, Clause, Formula, Lit, Var};
use std::collections::{BTreeSet, HashMap};

const ARB_BUDGET: usize = 8192;

pub struct ForcingCert {
    /// `(ante, then)` with `var(then) = y`, every `var(ante[i]) ∈ dep(y)`.
    pub clauses: HashMap<Var, Vec<(Vec<Lit>, Lit)>>,
    /// `(y, dep_row_lits, value)` — explicit table cells for undefined y.
    pub cells: Vec<(Var, Vec<Lit>, bool)>,
    pub rounds: usize,
}

pub fn validity_cegar(
    f: &Formula,
    undefined: &[Var],
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
) -> Option<ForcingCert> {
    let n = f.n_vars as usize;
    let m = f.clauses.len();
    let undef_set: BTreeSet<Var> = undefined.iter().copied().collect();

    // --- validity solver: Tseitin(¬matrix) over (U,E,aux,arbiters) -----
    let mut vclauses: Vec<Clause> = Vec::with_capacity(m + 1);
    let mut all_aux: Clause = Vec::with_capacity(m);
    for (i, c) in f.clauses.iter().enumerate() {
        let aux = (n + 1 + i) as Lit;
        for &l in c {
            vclauses.push(vec![-aux, -l]);
        }
        all_aux.push(aux);
    }
    vclauses.push(all_aux);
    let arb_base = n + m;
    let nv = arb_base + ARB_BUDGET;
    let mut validity = Cdcl::new(nv, &vclauses);
    for i in 1..=ARB_BUDGET {
        validity.set_decision((arb_base + i) as u32, false);
    }
    let mut vmodel = vec![0i8; nv + 1];

    // --- consistency solver: matrix(U,E) + arbiter links --------------
    let nc = n + ARB_BUDGET;
    let mut consist = Cdcl::new(nc, &f.clauses);
    for i in 1..=ARB_BUDGET {
        consist.set_decision((n + i) as u32, false);
    }
    let mut cmodel = vec![0i8; nc + 1];
    let mut scratch = vec![0i8; nc + 1];

    // --- arbiter solver: pure arbiter conflict clauses ----------------
    let mut arbsolve = Cdcl::new(ARB_BUDGET, &[]);
    for i in 1..=ARB_BUDGET {
        arbsolve.set_decision(i as u32, false);
    }
    let mut amodel = vec![0i8; ARB_BUDGET + 1];

    let exs: Vec<Var> = f.deps.keys().copied().collect();
    let dep_set: HashMap<Var, BTreeSet<Var>> =
        exs.iter().map(|&y| (y, f.deps[&y].clone())).collect();
    let univ: BTreeSet<Var> = f.universals.iter().copied().collect();

    let mut forcing: HashMap<Var, Vec<(Vec<Lit>, Lit)>> =
        exs.iter().map(|&y| (y, Vec::new())).collect();
    // (y, dep_row_key) → arbiter var index (1-based into arb space)
    let mut arb_of: HashMap<(Var, Vec<Lit>), usize> = HashMap::new();
    let mut arb_meta: Vec<(Var, Vec<Lit>)> = vec![(0, vec![])]; // 1-indexed
    let mut arb_assump: Vec<Lit> = Vec::new();

    let conf_budget: u64 = 100_000;
    let mut rounds = 0usize;
    if debug {
        eprintln!(
            "c [def] cegar start: |E|={} |undef|={} |C|={}",
            exs.len(),
            undefined.len(),
            m
        );
    }
    loop {
        if start.elapsed().as_secs_f64() >= deadline {
            if debug {
                eprintln!(
                    "c [def] cegar deadline: {} rounds, {} arbiters, {} forcing",
                    rounds,
                    arb_meta.len() - 1,
                    forcing.values().map(|v| v.len()).sum::<usize>()
                );
            }
            return None;
        }
        rounds += 1;

        // ---- validity counterexample under current arbiters ----------
        let sat = validity.solve(&arb_assump, &mut vmodel, conf_budget);
        if validity.budget_hit {
            return None;
        }
        if !sat {
            // ¬matrix unreachable under encoded Skolem → DQBF SAT.
            if debug {
                eprintln!(
                    "c [def] cegar SAT after {} rounds, {} forcing, {} arbiters",
                    rounds,
                    forcing.values().map(|v| v.len()).sum::<usize>(),
                    arb_meta.len() - 1
                );
            }
            let cells: Vec<(Var, Vec<Lit>, bool)> = (1..arb_meta.len())
                .map(|i| {
                    let (y, dep) = arb_meta[i].clone();
                    let val = arb_assump
                        .iter()
                        .find(|&&l| var(l) as usize == arb_base + i)
                        .map(|&l| l > 0)
                        .unwrap_or(false);
                    (y, dep, val)
                })
                .collect();
            return Some(ForcingCert { clauses: forcing, cells, rounds });
        }
        let u_assump: Vec<Lit> = f
            .universals
            .iter()
            .map(|&u| if vmodel[u as usize] >= 0 { u as Lit } else { -(u as Lit) })
            .collect();

        // ---- row model under U* + current arbiters -------------------
        let mut ca: Vec<Lit> = u_assump.clone();
        for &l in &arb_assump {
            // remap validity-space arbiter lit → consist-space (n+i)
            let ai = var(l) as usize - arb_base;
            ca.push(if l > 0 { (n + ai) as Lit } else { -((n + ai) as Lit) });
        }
        let row_sat = consist.solve(&ca, &mut cmodel, conf_budget);
        if consist.budget_hit {
            return None;
        }
        if !row_sat {
            // Conflict between U* and arbiter choices. Core ⊆ ca.
            let core = consist.last_core();
            let arb_core: Vec<Lit> = core
                .iter()
                .filter(|&&l| var(l) as usize > n)
                .map(|&l| {
                    let ai = var(l) as usize - n;
                    if l > 0 { ai as Lit } else { -(ai as Lit) }
                })
                .collect();
            if arb_core.is_empty() {
                // Genuine UNSAT row (matrix[U*,·] propositionally UNSAT).
                if debug {
                    eprintln!("c [def] cegar genuine UNSAT row at round {}", rounds);
                }
                return None;
            }
            // Learn ¬arb_core in arbsolve; re-pick arbiters.
            let conflict: Vec<Lit> = arb_core.iter().map(|&l| -l).collect();
            arbsolve.add_external(&conflict);
            if !arbsolve.solve(&[], &mut amodel, conf_budget) {
                if debug {
                    eprintln!("c [def] cegar arbiter space exhausted → no Skolem");
                }
                return None;
            }
            arb_assump.clear();
            for i in 1..arb_meta.len() {
                let l = if amodel[i] >= 0 { (arb_base + i) as Lit } else { -((arb_base + i) as Lit) };
                arb_assump.push(l);
            }
            continue;
        }

        // ---- learn forcing / allocate arbiters -----------------------
        // Target only existentials that *fix a violated clause*: for
        // each aux_i true in vmodel, pick one existential lit in
        // clause_i that cmodel satisfies. Pinning that lit via a
        // forcing clause repairs the counterexample with one
        // flip-check, instead of one per disagreeing existential.
        let mut targets: Vec<Var> = Vec::new();
        for (i, c) in f.clauses.iter().enumerate() {
            if vmodel[n + 1 + i] <= 0 {
                continue;
            }
            for &l in c {
                let v = var(l);
                if dep_set.contains_key(&v) && (cmodel[v as usize] > 0) == (l > 0) {
                    targets.push(v);
                    break;
                }
            }
        }
        targets.sort_unstable();
        targets.dedup();
        let mut learned_any = false;
        for &y in &targets {
            let want = cmodel[y as usize];
            let got = vmodel[y as usize];
            if want == got && got != 0 {
                continue;
            }
            let dep_lits: Vec<Lit> = dep_set[&y]
                .iter()
                .map(|&u| if cmodel[u as usize] > 0 { u as Lit } else { -(u as Lit) })
                .collect();
            if undef_set.contains(&y) {
                // Undefined-y with large dep: per-cell arbiters can't
                // saturate. Use a single *constant* arbiter (y ↔ a)
                // instead — sound when some constant Skolem works,
                // which is the common case for don't-care/miter bits.
                let cell_dep = if dep_lits.len() > 8 { vec![] } else { dep_lits.clone() };
                let key = (y, cell_dep.clone());
                let ai = *arb_of.entry(key.clone()).or_insert_with(|| {
                    arb_meta.push((y, cell_dep.clone()));
                    let idx = arb_meta.len() - 1;
                    if idx >= ARB_BUDGET {
                        return idx;
                    }
                    let av = (arb_base + idx) as Lit;
                    let ac = (n + idx) as Lit;
                    // cell_dep ∧ a → y  /  cell_dep ∧ ¬a → ¬y
                    let mut c1: Vec<Lit> = cell_dep.iter().map(|&l| -l).collect();
                    let mut c2 = c1.clone();
                    c1.push(-av); c1.push(y as Lit);
                    c2.push(av);  c2.push(-(y as Lit));
                    validity.add_external(&c1);
                    validity.add_external(&c2);
                    let mut d1: Vec<Lit> = cell_dep.iter().map(|&l| -l).collect();
                    let mut d2 = d1.clone();
                    d1.push(-ac); d1.push(y as Lit);
                    d2.push(ac);  d2.push(-(y as Lit));
                    consist.add_external(&d1);
                    consist.add_external(&d2);
                    arbsolve.set_decision(idx as u32, true);
                    arbsolve.set_phase(idx as u32, want);
                    arb_assump.push(if want > 0 { av } else { -av });
                    idx
                });
                if ai >= ARB_BUDGET {
                    if debug {
                        let mut by_y: HashMap<Var, usize> = HashMap::new();
                        for (yy, _) in &arb_meta[1..] { *by_y.entry(*yy).or_default() += 1; }
                        eprintln!("c [def] cegar arbiter budget exhausted at round {}: by_y={:?}", rounds, by_y);
                    }
                    return None;
                }
                learned_any = true;
                continue;
            }
            // Defined y: extract forcing clause via core.
            let mut a = dep_lits.clone();
            a.push(if want > 0 { -(y as Lit) } else { y as Lit });
            let flip_sat = consist.solve(&a, &mut scratch, 10_000);
            if consist.budget_hit {
                return None;
            }
            if flip_sat {
                // Padoa missed this y. Treat as undefined from here on.
                if debug {
                    eprintln!("c [def] cegar: y={} not actually defined; bail", y);
                }
                return None;
            }
            let then = if want > 0 { y as Lit } else { -(y as Lit) };
            let ante: Vec<Lit> = consist
                .last_core()
                .iter()
                .copied()
                .filter(|&l| univ.contains(&var(l)))
                .collect();
            let fc: Vec<Lit> = ante.iter().map(|&l| -l).chain(std::iter::once(then)).collect();
            validity.add_external(&fc);
            forcing.get_mut(&y).unwrap().push((ante, then));
            learned_any = true;
        }
        if !learned_any {
            if debug {
                eprintln!("c [def] cegar stalled at round {}", rounds);
            }
            return None;
        }
    }
}

/// Convert forcing clauses + arbiter cells to a truth-table Skolem when
/// every dep set fits; otherwise None (caller emits SAT-no-cert).
pub fn forcing_to_skolem(f: &Formula, cert: &ForcingCert, max_dep: usize) -> Option<Skolem> {
    let mut sk = Skolem::new();
    for (&y, d) in &f.deps {
        let nd = d.len();
        if nd > max_dep {
            return None;
        }
        let dvec: Vec<Var> = d.iter().copied().collect();
        let didx: HashMap<Var, usize> =
            dvec.iter().enumerate().map(|(i, &v)| (v, i)).collect();
        let n_rows = 1usize << nd;
        let mut tbl = vec![0u64; (n_rows + 63) / 64];
        if let Some(fcs) = cert.clauses.get(&y) {
            'row: for r in 0..n_rows {
                for (ante, then) in fcs {
                    if ante
                        .iter()
                        .all(|&l| ((r >> didx[&var(l)]) & 1 == 1) == (l > 0))
                    {
                        if *then > 0 {
                            tbl[r / 64] |= 1u64 << (r % 64);
                        }
                        continue 'row;
                    }
                }
            }
        }
        for (cy, dep, val) in &cert.cells {
            if *cy != y || !*val {
                continue;
            }
            let mut r = 0usize;
            for &l in dep {
                if l > 0 {
                    r |= 1 << didx[&var(l)];
                }
            }
            tbl[r / 64] |= 1u64 << (r % 64);
        }
        sk.insert(y, (tbl, nd));
    }
    Some(sk)
}
