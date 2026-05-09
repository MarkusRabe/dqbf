//! Given-clause saturation with proof recording.

use crate::aiger::Skolem;
use crate::formula::{var, Clause, Formula};
use crate::proof::{Proof, Step};
use crate::rules::{is_tautology, resolve, universal_reduce};
use std::collections::{HashMap, HashSet};
use std::time::Instant;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    Sat,
    Unsat,
    Unknown,
}

pub struct Config {
    pub max_clauses: usize,
    pub max_forks: usize,
    pub timeout_s: f64,
    pub extract_cert: bool,
    pub debug_expand: bool,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            max_clauses: 200_000,
            max_forks: 256,
            timeout_s: 10.0,
            extract_cert: true,
            debug_expand: false,
        }
    }
}

pub struct Output {
    pub verdict: Verdict,
    pub proof: Option<Proof>,
    pub skolem: Option<Skolem>,
    pub stats: String,
}

use std::cmp::Reverse;
use std::collections::BinaryHeap;

struct Db {
    clauses: Vec<Clause>,
    sig: Vec<u64>,
    dead: Vec<bool>,
    seen: HashSet<Clause>,
    proof: Proof,
    idx: HashMap<Clause, usize>,
    occ: HashMap<Lit, Vec<usize>>,
    queue: BinaryHeap<Reverse<(usize, usize)>>, // (len, ci)
    processed: Vec<bool>,
}

#[inline]
fn sig_of(c: &Clause) -> u64 {
    let mut s = 0u64;
    for &l in c {
        s |= 1u64 << ((l as i64).rem_euclid(64) as u32);
    }
    s
}

fn subsumes(a: &Clause, b: &Clause) -> bool {
    // a ⊆ b for sorted vecs
    let (mut i, mut j) = (0, 0);
    while i < a.len() {
        if j >= b.len() {
            return false;
        }
        match a[i].cmp(&b[j]) {
            std::cmp::Ordering::Less => return false,
            std::cmp::Ordering::Equal => {
                i += 1;
                j += 1;
            }
            std::cmp::Ordering::Greater => j += 1,
        }
    }
    true
}

impl Db {
    fn new() -> Self {
        Self {
            clauses: Vec::new(),
            sig: Vec::new(),
            dead: Vec::new(),
            seen: HashSet::new(),
            proof: Proof::default(),
            idx: HashMap::new(),
            occ: HashMap::new(),
            queue: BinaryHeap::new(),
            processed: Vec::new(),
        }
    }
    fn forward_subsumed(&self, c: &Clause, csig: u64) -> bool {
        if c.is_empty() {
            return false;
        }
        let best = c
            .iter()
            .min_by_key(|&&l| self.occ.get(&l).map(|v| v.len()).unwrap_or(0))
            .copied()
            .unwrap();
        if let Some(cands) = self.occ.get(&best) {
            for &di in cands {
                if !self.dead[di]
                    && (self.sig[di] & !csig) == 0
                    && self.clauses[di].len() <= c.len()
                    && subsumes(&self.clauses[di], c)
                {
                    return true;
                }
            }
        }
        false
    }

    fn compact_occ(&mut self) {
        for list in self.occ.values_mut() {
            list.retain(|&di| !self.dead[di]);
        }
    }
    fn backward_subsume(&mut self, c: &Clause, csig: u64, self_ci: usize) {
        if c.is_empty() {
            return;
        }
        let best = c
            .iter()
            .min_by_key(|&&l| self.occ.get(&l).map(|v| v.len()).unwrap_or(0))
            .copied()
            .unwrap();
        if let Some(cands) = self.occ.get(&best) {
            for &di in cands {
                if di != self_ci
                    && !self.dead[di]
                    && (csig & !self.sig[di]) == 0
                    && self.clauses[di].len() >= c.len()
                    && subsumes(c, &self.clauses[di])
                {
                    self.dead[di] = true;
                }
            }
        }
    }
    fn record(&mut self, c: &Clause, s: Step) -> usize {
        if let Some(&i) = self.idx.get(c) {
            return i;
        }
        let i = self.proof.add(s);
        self.idx.insert(c.clone(), i);
        i
    }
    fn activate(&mut self, c: Clause) {
        if !self.seen.insert(c.clone()) {
            return;
        }
        let clen = c.len();
        let csig = sig_of(&c);
        if self.forward_subsumed(&c, csig) {
            return;
        }
        let ci = self.clauses.len();
        for &l in &c {
            self.occ.entry(l).or_default().push(ci);
        }
        self.sig.push(csig);
        self.dead.push(false);
        self.processed.push(false);
        self.queue.push(Reverse((clen, ci)));
        self.clauses.push(c.clone());
        if clen <= 5 {
            self.backward_subsume(&c, csig, ci);
        }
    }
    fn admit(&mut self, c: Clause, s: Step) -> usize {
        let i = self.record(&c, s);
        self.activate(c);
        i
    }
}

use crate::formula::Lit;

pub fn solve(f: &Formula, cfg: &Config) -> Output {
    let start = Instant::now();
    let mut g = f.clone();
    let mut db = Db::new();

    // BCE for saturation (nu=0 → no reconstruction-cost cap; can fully
    // empty). The cert path needs a separately-capped BCE so reconstruct
    // stays sub-exponential at high |U|.
    let sat_bce = if g.universals.len() < 64 {
        crate::bce::dqbf_bce(&g, 0)
    } else {
        crate::bce::BceResult {
            clauses: g.clauses.clone(),
            stack: Vec::new(),
            n_ate: 0,
        }
    };
    let nu_expand = g.universals.len().min(16);
    let cert_bce = crate::bce::dqbf_bce(&g, nu_expand);
    if cfg.debug_expand {
        eprintln!(
            "c [bce] |C|={}→{} (sat_bce removed {}, cert_bce removed {})",
            g.clauses.len(),
            sat_bce.clauses.len(),
            sat_bce.stack.len(),
            cert_bce.stack.len()
        );
    }
    for c in &sat_bce.clauses {
        if is_tautology(c) {
            continue;
        }
        let ai = db.record(c, Step::axiom(c));
        let rc = universal_reduce(&g, c);
        if rc != *c {
            db.record(&rc, Step::ured(&rc, ai));
        }
        db.activate(rc);
    }
    if db.seen.contains(&Clause::new()) {
        return Output {
            verdict: Verdict::Unsat,
            proof: Some(db.proof),
            skolem: None,
            stats: "empty in input".into(),
        };
    }
    // BCE emptied the matrix → SAT. With cert if reconstruction is
    // affordable (|U|≤16); otherwise SAT-no-cert.
    if sat_bce.clauses.is_empty() {
        if cfg.extract_cert && f.universals.len() <= 16 {
            let mut sk = crate::aiger::Skolem::new();
            for (&y, d) in &f.deps {
                let nd = d.len();
                sk.insert(
                    y,
                    crate::aiger::SkolemFn::Table(vec![0u64; ((1usize << nd) + 63) / 64], nd),
                );
            }
            crate::bce::reconstruct(&mut sk, f, &sat_bce.stack);
            return Output {
                verdict: Verdict::Sat,
                proof: None,
                skolem: Some(sk),
                stats: "BCE empties matrix".into(),
            };
        }
        // |U|>16: truth-table reconstruction is unaffordable, but the
        // BCE stack repair lifts to a circuit when dep sets are nested.
        let sk = if cfg.extract_cert {
            crate::bce::reconstruct_circuit(f, &sat_bce.stack)
        } else {
            None
        };
        return Output {
            verdict: Verdict::Sat,
            proof: None,
            skolem: sk,
            stats: "BCE empties matrix (circuit reconstruction)".into(),
        };
    }
    let mut forks = 0usize;
    let mut cdcl = crate::cdcl::Cdcl::new(f.n_vars as usize, &cert_bce.clauses);
    let mut ex = crate::expand_state::ExpandState::new(f, cert_bce.stack);
    let mut fed_upto = 0usize;
    let mut last_bce_at = db.clauses.len();
    let mut known_unsat = false;
    let mut expand_done = !cfg.extract_cert;

    // Interleaved scheduler: alternate expand and saturate slices,
    // feeding saturate's short derived clauses into expand's CDCL.
    // ExpandState is *resumable* — each slice continues from where
    // the previous one yielded. First expand slice gets most of the
    // budget so the common case (decides outright) is unpenalized;
    // subsequent slices are smaller and grow geometrically.
    let mut slice = cfg.timeout_s * 0.7;
    let mut first = true;
    loop {
        let now = start.elapsed().as_secs_f64();
        if now >= cfg.timeout_s {
            return bail(&db, forks, known_unsat);
        }

        // ---- Expand slice (resumable) ----
        if !expand_done && !known_unsat {
            let ex_deadline = now + slice.min(cfg.timeout_s - now);
            match ex.step(f, &mut cdcl, ex_deadline, &start, cfg.debug_expand) {
                crate::expand_state::Step::Sat(sk) => {
                    return Output {
                        verdict: Verdict::Sat,
                        proof: None,
                        skolem: sk,
                        stats: format!("expand (slice {:.2}s)", slice),
                    };
                }
                crate::expand_state::Step::Unsat => {
                    known_unsat = true;
                    expand_done = true;
                }
                crate::expand_state::Step::UnsatRow(row) => {
                    let now = start.elapsed().as_secs_f64();
                    let dl = (now + 1.5).min(cfg.timeout_s - 0.2);
                    let proof = if dl > now {
                        crate::proof_emit::reprove_row_unsat(f, &row, 500_000, dl, &start)
                    } else {
                        None
                    };
                    return Output {
                        verdict: Verdict::Unsat,
                        proof,
                        skolem: None,
                        stats: "expand-row-unsat".into(),
                    };
                }
                crate::expand_state::Step::Done => expand_done = true,
                crate::expand_state::Step::Pending => {}
            }
        }

        // ---- Saturate slice ----
        let now = start.elapsed().as_secs_f64();
        let sat_slice = if known_unsat {
            // Verdict known; saturate is best-effort cert recovery.
            // 0.5 s is enough for the easy cases; 2 s here cost ~170
            // borderline solves under j=48 for ~17 extra certs.
            (cfg.timeout_s - now).min(now * 1.5).clamp(0.05, 0.5)
        } else {
            slice.min(cfg.timeout_s - now)
        };
        if let Some(out) = saturate(
            &mut db,
            &mut g,
            &start,
            now + sat_slice,
            cfg,
            &mut forks,
            known_unsat,
        ) {
            // saturate decided (UNSAT+proof, or SAT-via-saturation).
            if out.verdict == Verdict::Sat && known_unsat {
                eprintln!("c WARNING: expand-UNSAT vs saturation-SAT");
                return Output {
                    verdict: Verdict::Unknown,
                    proof: None,
                    skolem: None,
                    stats: "contradiction".into(),
                };
            }
            return out;
        }
        if known_unsat {
            return bail(&db, forks, true);
        }

        // ---- Cross-feed: short Q-resolution-derived clauses → CDCL ----
        // Saturate's FEx/SFEx forks introduce vars beyond expand-CDCL's
        // n_vars; clauses mentioning those would index past `value[]`.
        let nv = f.n_vars as Lit;
        for c in &db.clauses[fed_upto..] {
            if c.len() <= 4 && c.iter().all(|&l| crate::formula::var(l) as Lit <= nv) {
                cdcl.add_external(c);
            }
        }
        fed_upto = db.clauses.len();

        // ---- Incremental BCE on the live Db (saturate's working set) ----
        // Derived clauses can render earlier ones blocked. Sound: BCE
        // preserves equisat; .frp steps stay (they're already recorded),
        // we just stop those clauses participating in future resolutions.
        if db.clauses.len() > last_bce_at + last_bce_at / 2 + 256 {
            let n_killed = incremental_bce(&mut db, f);
            if cfg.debug_expand && n_killed > 0 {
                eprintln!(
                    "c [bce-inc] killed {} of {} live clauses",
                    n_killed,
                    db.clauses.len()
                );
            }
            last_bce_at = db.clauses.len();
        }

        if first {
            slice = (cfg.timeout_s * 0.1).clamp(0.2, 1.0);
            first = false;
        } else {
            slice = (slice * 1.6).min(cfg.timeout_s * 0.4);
        }
    }
}

/// Run the given-clause saturation loop until a verdict (Some) or the
/// deadline / clause / fork budget (None). Mutates db and g in place so
/// a later call resumes from where this one left off.
fn saturate(
    db: &mut Db,
    g: &mut Formula,
    start: &Instant,
    sat_deadline: f64,
    cfg: &Config,
    forks: &mut usize,
    known_unsat: bool,
) -> Option<Output> {
    let mut tick = 0u64;
    loop {
        let mut found_empty = false;
        while let Some(item @ Reverse((_, cursor))) = db.queue.pop() {
            if start.elapsed().as_secs_f64() > sat_deadline || db.clauses.len() > cfg.max_clauses {
                db.queue.push(item);
                return None;
            }
            if db.dead[cursor] || db.processed[cursor] {
                continue;
            }
            db.processed[cursor] = true;
            if cursor & 0x7ff == 0x7ff {
                db.compact_occ();
            }
            let c = db.clauses[cursor].clone();
            let ci = db.idx[&c];
            'lits: for &l in &c {
                let partners: Vec<usize> = db
                    .occ
                    .get(&(-l))
                    .map(|v| {
                        v.iter()
                            .copied()
                            .filter(|&di| db.processed[di] && !db.dead[di])
                            .collect()
                    })
                    .unwrap_or_default();
                for di in partners {
                    tick += 1;
                    if tick & 0xffff == 0
                        && (start.elapsed().as_secs_f64() > sat_deadline
                            || db.clauses.len() > cfg.max_clauses)
                    {
                        return None;
                    }
                    if let Some(r) = resolve(&c, &db.clauses[di], var(l)) {
                        let rr = universal_reduce(g, &r);
                        if db.seen.contains(&rr) {
                            continue;
                        }
                        let dpi = db.idx[&db.clauses[di]];
                        let step = Step::res(&rr, ci, dpi, var(l));
                        if rr.is_empty() {
                            db.admit(rr, step);
                            found_empty = true;
                            break 'lits;
                        }
                        db.admit(rr, step);
                    }
                }
            }
            if found_empty {
                break;
            }
        }
        if found_empty {
            return Some(Output {
                verdict: Verdict::Unsat,
                proof: {
                    let mut p = std::mem::take(&mut db.proof);
                    p.compact();
                    Some(p)
                },
                skolem: None,
                stats: format!("⊥ after {} clauses, {} forks", db.clauses.len(), forks),
            });
        }
        if start.elapsed().as_secs_f64() > sat_deadline || db.clauses.len() > cfg.max_clauses {
            return None;
        }
        // saturated; try a fork
        let mut order: Vec<usize> = (0..db.clauses.len()).filter(|&i| !db.dead[i]).collect();
        order.sort_by_key(|&i| db.clauses[i].len());
        let mut forked = false;
        for &i in &order {
            let c = db.clauses[i].clone();
            if let Some((part, fr)) = crate::rules::choose_fork(g, &c, known_unsat) {
                let src = db.idx[&c];
                for cl in [&fr.left, &fr.right] {
                    db.record(cl, Step::fex(cl, src, part.clone(), fr.fresh));
                    let rcl = universal_reduce(g, cl);
                    if rcl != *cl {
                        let pi = db.idx[cl];
                        db.record(&rcl, Step::ured(&rcl, pi));
                    }
                    db.activate(rcl);
                }
                forked = true;
                break;
            }
        }
        // SFEx (journal §6 cycle-breaking) when FEx found nothing. The
        // O(|db|·|exs|²) scan would eat the interleaved CEGAR slice on
        // large matrices, so gate on known_unsat there; small formulas
        // (dep_cycle has |C|=82) can always afford it.
        if !forked && (known_unsat || db.clauses.len() < 200) {
            for &i in &order {
                let c = db.clauses[i].clone();
                if let Some((part, c3, fr)) = crate::rules::choose_sfork(g, &c) {
                    let src = db.idx[&c];
                    for cl in [&fr.left, &fr.right] {
                        db.record(cl, Step::sfex(cl, src, part.clone(), c3.clone(), fr.fresh));
                        let rcl = universal_reduce(g, cl);
                        if rcl != *cl {
                            let pi = db.idx[cl];
                            db.record(&rcl, Step::ured(&rcl, pi));
                        }
                        db.activate(rcl);
                    }
                    forked = true;
                    break;
                }
            }
        }
        if !forked {
            if known_unsat {
                // Expand says UNSAT, saturation says SAT — contradiction.
                // Don't trust either; bail UNKNOWN.
                eprintln!("c WARNING: expand-UNSAT vs saturation-SAT");
                return Some(Output {
                    verdict: Verdict::Unknown,
                    proof: None,
                    skolem: None,
                    stats: "expand/saturation contradiction".into(),
                });
            }
            return Some(Output {
                verdict: Verdict::Sat,
                proof: None,
                skolem: None,
                stats: format!("saturated: {} clauses", db.clauses.len()),
            });
        }
        *forks += 1;
        if *forks >= cfg.max_forks {
            return None;
        }
    }
}

/// Re-run BCE on Db's live clause set; mark newly-blocked clauses dead.
/// Returns how many were killed.
fn incremental_bce(db: &mut Db, f: &Formula) -> usize {
    let live: Vec<(usize, Clause)> = db
        .clauses
        .iter()
        .enumerate()
        .filter(|&(ci, _)| !db.dead[ci])
        .map(|(ci, c)| (ci, c.clone()))
        .collect();
    if live.is_empty() {
        return 0;
    }
    // Build a temp Formula with the live clauses + original prefix. FEx
    // forks introduce vars > f.n_vars; size for those (BCE treats them
    // as existentials with empty dep, so they're never the witness).
    let max_var = live
        .iter()
        .flat_map(|(_, c)| c.iter().map(|&l| crate::formula::var(l)))
        .max()
        .unwrap_or(f.n_vars);
    let tmp = Formula::new(
        max_var.max(f.n_vars),
        f.universals.clone(),
        f.deps.clone(),
        live.iter().map(|(_, c)| c.clone()).collect(),
    );
    let res = crate::bce::dqbf_bce(&tmp, 0);
    // Surviving clauses by content; kill the rest in Db.
    let survived: std::collections::HashSet<Clause> = res.clauses.into_iter().collect();
    let mut n = 0usize;
    for (ci, c) in live {
        if !survived.contains(&c) {
            db.dead[ci] = true;
            n += 1;
        }
    }
    n
}

fn bail(db: &Db, forks: usize, known_unsat: bool) -> Output {
    Output {
        verdict: if known_unsat {
            Verdict::Unsat
        } else {
            Verdict::Unknown
        },
        proof: None,
        skolem: None,
        stats: format!(
            "{}: {} clauses, {} forks",
            if known_unsat {
                "expand-UNSAT (no .frp)"
            } else {
                "budget"
            },
            db.clauses.len(),
            forks
        ),
    }
}
