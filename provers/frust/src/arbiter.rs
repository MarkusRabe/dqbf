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

pub enum CegarOut {
    Sat(ForcingCert),
    /// matrix[U*,·] propositionally UNSAT — carries the universal row.
    UnsatRow(Vec<Lit>),
    /// arbsolve exhausted — every Skolem fails some row.
    Unsat,
    Bail,
    Pending,
}

/// Persisted validity-CEGAR state so slices accumulate instead of
/// restarting (iter16: bcd_ctr needs ~12s of arbsolve search; one
/// 4.9 s slice isn't enough but three are).
pub struct CegarState {
    n: usize,
    arb_base: usize,
    validity: Cdcl,
    vmodel: Vec<i8>,
    consist: Cdcl,
    cmodel: Vec<i8>,
    scratch: Vec<i8>,
    arbsolve: Cdcl,
    amodel: Vec<i8>,
    exs: Vec<Var>,
    dep_set: HashMap<Var, BTreeSet<Var>>,
    univ: BTreeSet<Var>,
    undef_set: BTreeSet<Var>,
    forcing: HashMap<Var, Vec<(Vec<Lit>, Lit)>>,
    arb_of: HashMap<(Var, Vec<Lit>), usize>,
    arb_meta: Vec<Vec<(Var, Vec<Lit>)>>,
    arb_assump: Vec<Lit>,
    any_const_arbiter: bool,
    cell_dep_cap: usize,
    /// Consistency-shape pairs: y → (y', dep_bijection) where the
    /// formula encodes `(⋀ d_i↔d'_i) → (y↔y')`. One arbiter cell
    /// then links both — halves the cell count and lets arbsolve see
    /// the cross-row constraint directly instead of via |dep| rounds.
    pub partner: HashMap<Var, (Var, Vec<(Var, Var)>)>,
    rounds: usize,
}

/// Detect (y,y') pairs with disjoint same-size deps where the formula
/// provably encodes `(⋀ dᵢ↔d'ᵢ) → (y↔y')`. Sound check via a fresh
/// 2-copy CDCL (Padoa-style): link dᵢ↔d'ᵢ unconditionally, then
/// `matrix ∧ y ∧ ¬y'` UNSAT (and symmetric) ⇒ the matrix forces y↔y'
/// whenever dep(y) and dep(y') agree positionally. Only then is
/// sharing one arbiter cell sound.
fn detect_partners(f: &Formula, undef: &[Var]) -> HashMap<Var, (Var, Vec<(Var, Var)>)> {
    use std::collections::BTreeMap;
    let mut by_size: BTreeMap<usize, Vec<Var>> = BTreeMap::new();
    for &y in undef {
        let d = &f.deps[&y];
        if !d.is_empty() {
            by_size.entry(d.len()).or_default().push(y);
        }
    }
    let n = f.n_vars as usize;
    // One incremental CDCL with selector-guarded link clauses for every
    // ordered universal pair (u,v): sel_{u,v} → (u ↔ v). Consistency of
    // (y, y') under bijection bij is then `solve(sel_{bij} ∪ {y, ¬y'})`
    // and `solve(sel_{bij} ∪ {¬y, y'})` both UNSAT.
    let us: Vec<Var> = f.universals.iter().copied().collect();
    let n_sel = us.len() * us.len();
    let sel = |a: Var, b: Var| -> Lit {
        let ia = us.iter().position(|&u| u == a).unwrap();
        let ib = us.iter().position(|&u| u == b).unwrap();
        (n + 1 + ia * us.len() + ib) as Lit
    };
    let mut cls: Vec<Clause> = f.clauses.clone();
    for &a in &us {
        for &b in &us {
            let s = sel(a, b);
            cls.push(vec![-s, a as Lit, -(b as Lit)]);
            cls.push(vec![-s, -(a as Lit), b as Lit]);
        }
    }
    let mut chk = Cdcl::new(n + n_sel, &cls);
    for i in 1..=n_sel {
        chk.set_decision((n + i) as u32, false);
    }
    let mut sm = vec![0i8; n + n_sel + 1];
    let mut out: HashMap<Var, (Var, Vec<(Var, Var)>)> = HashMap::new();
    for ys in by_size.values() {
        let mut taken: BTreeSet<Var> = BTreeSet::new();
        for i in 0..ys.len() {
            if taken.contains(&ys[i]) {
                continue;
            }
            let di: Vec<Var> = f.deps[&ys[i]].iter().copied().collect();
            for &yj in &ys[i + 1..] {
                if taken.contains(&yj) {
                    continue;
                }
                let dj: Vec<Var> = f.deps[&yj].iter().copied().collect();
                if di.iter().any(|u| f.deps[&yj].contains(u)) {
                    continue;
                }
                let bij: Vec<(Var, Var)> = di.iter().copied().zip(dj.iter().copied()).collect();
                let sels: Vec<Lit> = bij.iter().map(|&(a, b)| sel(a, b)).collect();
                let mut a1 = sels.clone();
                a1.push(ys[i] as Lit);
                a1.push(-(yj as Lit));
                let mut a2 = sels;
                a2.push(-(ys[i] as Lit));
                a2.push(yj as Lit);
                if chk.solve(&a1, &mut sm, 5_000)
                    || chk.budget_hit
                    || chk.solve(&a2, &mut sm, 5_000)
                    || chk.budget_hit
                {
                    continue;
                }
                out.insert(ys[i], (yj, bij.clone()));
                out.insert(yj, (ys[i], bij.iter().map(|&(a, b)| (b, a)).collect()));
                taken.insert(ys[i]);
                taken.insert(yj);
                break;
            }
        }
    }
    out
}

impl CegarState {
    pub fn new(f: &Formula, undefined: &[Var]) -> Self {
        let n = f.n_vars as usize;
        let m = f.clauses.len();
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
        let nc = n + ARB_BUDGET;
        let mut consist = Cdcl::new(nc, &f.clauses);
        for i in 1..=ARB_BUDGET {
            consist.set_decision((n + i) as u32, false);
        }
        let mut arbsolve = Cdcl::new(ARB_BUDGET, &[]);
        for i in 1..=ARB_BUDGET {
            arbsolve.set_decision(i as u32, false);
        }
        let exs: Vec<Var> = f.deps.keys().copied().collect();
        Self {
            n,
            arb_base,
            vmodel: vec![0i8; nv + 1],
            validity,
            cmodel: vec![0i8; nc + 1],
            scratch: vec![0i8; nc + 1],
            consist,
            amodel: vec![0i8; ARB_BUDGET + 1],
            arbsolve,
            dep_set: exs.iter().map(|&y| (y, f.deps[&y].clone())).collect(),
            univ: f.universals.iter().copied().collect(),
            undef_set: undefined.iter().copied().collect(),
            forcing: exs.iter().map(|&y| (y, Vec::new())).collect(),
            exs,
            arb_of: HashMap::new(),
            arb_meta: vec![vec![]],
            arb_assump: Vec::new(),
            any_const_arbiter: false,
            cell_dep_cap: (ARB_BUDGET / undefined.len().max(1))
                .next_power_of_two()
                .trailing_zeros()
                .min(12) as usize,
            partner: detect_partners(f, undefined),
            rounds: 0,
        }
    }
}

pub fn validity_cegar(
    st: &mut CegarState,
    f: &Formula,
    deadline: f64,
    start: &std::time::Instant,
    debug: bool,
) -> CegarOut {
    let CegarState {
        n,
        arb_base,
        validity,
        vmodel,
        consist,
        cmodel,
        scratch,
        arbsolve,
        amodel,
        exs,
        dep_set,
        univ,
        undef_set,
        forcing,
        arb_of,
        arb_meta,
        arb_assump,
        any_const_arbiter,
        cell_dep_cap,
        partner,
        rounds,
    } = st;
    let cell_dep_cap = *cell_dep_cap;
    let (n, arb_base) = (*n, *arb_base);
    let conf_budget: u64 = 100_000;
    if debug && *rounds == 0 {
        eprintln!(
            "c [def] cegar start: |E|={} |undef|={} |C|={}",
            exs.len(),
            undef_set.len(),
            f.clauses.len()
        );
    }
    loop {
        if start.elapsed().as_secs_f64() >= deadline {
            if debug {
                eprintln!(
                    "c [def] cegar pending: {} rounds, {} arbiters, {} forcing",
                    rounds,
                    arb_meta.len() - 1,
                    forcing.values().map(|v| v.len()).sum::<usize>()
                );
            }
            return CegarOut::Pending;
        }
        *rounds += 1;

        // ---- validity counterexample under current arbiters ----------
        let sat = validity.solve(&arb_assump, vmodel, conf_budget);
        if validity.budget_hit {
            return CegarOut::Bail;
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
                .flat_map(|i| {
                    let val = arb_assump
                        .iter()
                        .find(|&&l| var(l) as usize == arb_base + i)
                        .map(|&l| l > 0)
                        .unwrap_or(false);
                    arb_meta[i]
                        .iter()
                        .map(move |(y, dep)| (*y, dep.clone(), val))
                        .collect::<Vec<_>>()
                })
                .collect();
            return CegarOut::Sat(ForcingCert {
                clauses: std::mem::take(forcing),
                cells,
                rounds: *rounds,
            });
        }
        let u_assump: Vec<Lit> = f
            .universals
            .iter()
            .map(|&u| if vmodel[u as usize] >= 0 { u as Lit } else { -(u as Lit) })
            .collect();

        // ---- row model under U* + current arbiters -------------------
        let mut ca: Vec<Lit> = u_assump.clone();
        for &l in arb_assump.iter() {
            // remap validity-space arbiter lit → consist-space (n+i)
            let ai = var(l) as usize - arb_base;
            ca.push(if l > 0 { (n + ai) as Lit } else { -((n + ai) as Lit) });
        }
        let row_sat = consist.solve(&ca, cmodel, conf_budget);
        if consist.budget_hit {
            return CegarOut::Bail;
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
                // Core ⊆ universals: matrix[U*,·] propositionally
                // UNSAT under consist (which has only original clauses
                // + arbiter links; links inactive when arb_core empty).
                if debug {
                    eprintln!("c [def] cegar UNSAT row at round {}", rounds);
                }
                return CegarOut::UnsatRow(u_assump);
            }
            // Learn ¬arb_core in arbsolve; re-pick arbiters.
            let conflict: Vec<Lit> = arb_core.iter().map(|&l| -l).collect();
            arbsolve.add_external(&conflict);
            if !arbsolve.solve(&[], amodel, conf_budget) {
                // Every per-cell arbiter assignment hits some U* with
                // matrix[U*, cells, rest-free] UNSAT — so every Skolem
                // fails. Sound only when arbiters cover full cells:
                // a constant arbiter restricts the search to constant-S_y,
                // missing non-constant Skolems.
                if debug {
                    eprintln!(
                        "c [def] cegar arbiter space exhausted (const={})",
                        any_const_arbiter
                    );
                }
                return if *any_const_arbiter {
                    CegarOut::Bail
                } else {
                    CegarOut::Unsat
                };
            }
            arb_assump.clear();
            for i in 1..arb_meta.len() {
                let l = if amodel[i] >= 0 { (arb_base + i) as Lit } else { -((arb_base + i) as Lit) };
                arb_assump.push(l);
            }
            continue;
        }

        // ---- learn forcing / allocate arbiters -----------------------
        // Round 1: seed with a forcing clause per existential so
        // validity starts close to fully constrained. Later rounds
        // only refine where vmodel still disagrees.
        let eager = *rounds == 1;
        let mut learned_any = false;
        for &y in exs.iter() {
            let want = cmodel[y as usize];
            let got = vmodel[y as usize];
            if !eager && want == got && got != 0 {
                continue;
            }
            let dep_lits: Vec<Lit> = dep_set[&y]
                .iter()
                .map(|&u| if cmodel[u as usize] > 0 { u as Lit } else { -(u as Lit) })
                .collect();
            // Try a forcing clause first unless Padoa already ruled y
            // undefined (then the flip-check is wasted work).
            if !undef_set.contains(&y) {
                let mut a = dep_lits.clone();
                a.push(if want > 0 { -(y as Lit) } else { y as Lit });
                let flip_sat = consist.solve(&a, scratch, 10_000);
                if consist.budget_hit {
                    return CegarOut::Bail;
                }
                if !flip_sat {
                    let then = if want > 0 { y as Lit } else { -(y as Lit) };
                    let ante: Vec<Lit> = consist
                        .last_core()
                        .iter()
                        .copied()
                        .filter(|&l| univ.contains(&var(l)))
                        .collect();
                    let fc: Vec<Lit> =
                        ante.iter().map(|&l| -l).chain(std::iter::once(then)).collect();
                    validity.add_external(&fc);
                    forcing.get_mut(&y).unwrap().push((ante, then));
                    learned_any = true;
                    continue;
                }
                // flip-SAT: y not determined by dep(y) alone (Padoa's
                // fixpoint linked extra z's). Fall through to arbiter.
            }
            // Arbiter: per-cell when |dep| fits the per-undef share of
            // ARB_BUDGET; else a single constant.
            let cell_dep = if dep_lits.len() > cell_dep_cap {
                *any_const_arbiter = true;
                vec![]
            } else {
                dep_lits.clone()
            };
            // For partnered y, key on the canonical (lower-var) side so
            // both share one cell. Link clauses are added for *both*
            // y and y' under their respective cell_deps; arb_meta keeps
            // both so cert reconstruction can read either side.
            let (key_y, key_dep, links): (Var, Vec<Lit>, Vec<(Var, Vec<Lit>)>) =
                match partner.get(&y) {
                    Some((yp, bij)) if !cell_dep.is_empty() => {
                        let bm: HashMap<Var, Var> = bij.iter().copied().collect();
                        let cell_dep_p: Vec<Lit> = cell_dep
                            .iter()
                            .map(|&l| {
                                let v = var(l);
                                let vp = *bm.get(&v).unwrap_or(&v) as Lit;
                                if l > 0 { vp } else { -vp }
                            })
                            .collect();
                        if y < *yp {
                            (y, cell_dep.clone(), vec![(y, cell_dep.clone()), (*yp, cell_dep_p)])
                        } else {
                            (*yp, cell_dep_p.clone(), vec![(*yp, cell_dep_p), (y, cell_dep.clone())])
                        }
                    }
                    _ => (y, cell_dep.clone(), vec![(y, cell_dep.clone())]),
                };
            let key = (key_y, key_dep);
            let ai = *arb_of.entry(key.clone()).or_insert_with(|| {
                arb_meta.push(links.clone());
                let idx = arb_meta.len() - 1;
                if idx >= ARB_BUDGET {
                    return idx;
                }
                let av = (arb_base + idx) as Lit;
                let ac = (n + idx) as Lit;
                for (yl, cd) in &links {
                    let mut c1: Vec<Lit> = cd.iter().map(|&l| -l).collect();
                    let mut c2 = c1.clone();
                    c1.push(-av); c1.push(*yl as Lit);
                    c2.push(av);  c2.push(-(*yl as Lit));
                    validity.add_external(&c1);
                    validity.add_external(&c2);
                    let mut d1: Vec<Lit> = cd.iter().map(|&l| -l).collect();
                    let mut d2 = d1.clone();
                    d1.push(-ac); d1.push(*yl as Lit);
                    d2.push(ac);  d2.push(-(*yl as Lit));
                    consist.add_external(&d1);
                    consist.add_external(&d2);
                }
                arbsolve.set_decision(idx as u32, true);
                arbsolve.set_phase(idx as u32, want);
                arb_assump.push(if want > 0 { av } else { -av });
                idx
            });
            if ai >= ARB_BUDGET {
                if debug {
                    eprintln!("c [def] cegar arbiter budget exhausted at round {}", rounds);
                }
                return CegarOut::Bail;
            }
            learned_any = true;
        }
        if !learned_any {
            if debug {
                eprintln!("c [def] cegar stalled at round {}", rounds);
            }
            return CegarOut::Bail;
        }
    }
}

/// Build a Skolem from forcing clauses + arbiter cells. Uses truth
/// tables for |dep|≤max_dep (BDD-memoized in AIGER); larger deps go
/// out as a priority-decoder circuit so cert size stays linear in the
/// number of forcing clauses rather than 2^|dep|.
pub fn forcing_to_skolem(f: &Formula, cert: &ForcingCert, max_dep: usize) -> Option<Skolem> {
    use crate::aiger::SkolemFn;
    let mut sk = Skolem::new();
    for (&y, d) in &f.deps {
        let nd = d.len();
        // Clause-form: forcing clauses first (defined-y), then arbiter
        // cells (undefined-y). validity-CEGAR guarantees the regions
        // don't conflict, so first-match is well-defined.
        let mut cubes: Vec<(Vec<Lit>, bool)> = Vec::new();
        if let Some(fcs) = cert.clauses.get(&y) {
            for (ante, then) in fcs {
                cubes.push((ante.clone(), *then > 0));
            }
        }
        for (cy, cdep, val) in &cert.cells {
            if *cy == y {
                cubes.push((cdep.clone(), *val));
            }
        }
        if nd > max_dep {
            sk.insert(y, SkolemFn::Clauses(cubes));
            continue;
        }
        // Small dep: materialise the table so BCE-reconstruct (which
        // only handles tables) and the Shannon-memo cert path apply.
        let dvec: Vec<Var> = d.iter().copied().collect();
        let didx: HashMap<Var, usize> =
            dvec.iter().enumerate().map(|(i, &v)| (v, i)).collect();
        let n_rows = 1usize << nd;
        let mut tbl = vec![0u64; n_rows.div_ceil(64)];
        'row: for r in 0..n_rows {
            for (ante, val) in &cubes {
                if ante
                    .iter()
                    .all(|&l| ((r >> didx[&var(l)]) & 1 == 1) == (l > 0))
                {
                    if *val {
                        tbl[r / 64] |= 1u64 << (r % 64);
                    }
                    continue 'row;
                }
            }
        }
        sk.insert(y, SkolemFn::Table(tbl, nd));
    }
    Some(sk)
}
