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
                sk.insert(y, (vec![0u64; ((1usize << nd) + 63) / 64], nd));
            }
            crate::bce::reconstruct(&mut sk, f, &sat_bce.stack);
            return Output {
                verdict: Verdict::Sat,
                proof: None,
                skolem: Some(sk),
                stats: "BCE empties matrix".into(),
            };
        }
        return Output {
            verdict: Verdict::Sat,
            proof: None,
            skolem: None,
            stats: "BCE empties matrix (no cert at |U|>16)".into(),
        };
    }
    let mut forks = 0usize;
    let mut cdcl = crate::cdcl::Cdcl::new(f.n_vars as usize, &cert_bce.clauses);
    let mut fed_upto = 0usize;
    let mut known_unsat = false;
    let mut unsat_row: Option<u32> = None;
    let mut candidate: Vec<Lit> = Vec::new();

    // Interleaved scheduler: alternate expand and saturate slices,
    // feeding saturate's short derived clauses into expand's CDCL.
    // First expand slice gets a generous budget so the common case
    // (expand decides immediately) isn't penalized; subsequent slices
    // grow geometrically.
    let mut slice = (cfg.timeout_s * 0.5).clamp(0.5, 4.0);
    let mut first = true;
    loop {
        let now = start.elapsed().as_secs_f64();
        if now >= cfg.timeout_s {
            return bail(&db, forks, known_unsat);
        }

        // ---- Expand slice ----
        if cfg.extract_cert && !known_unsat {
            let ex_start = Instant::now();
            let ex_budget = slice.min(cfg.timeout_s - now);
            if let Some(sk) = crate::expand::try_expand(
                f,
                &mut cdcl,
                &cert_bce.stack,
                ex_budget,
                &ex_start,
                cfg.debug_expand,
                &mut unsat_row,
                &mut candidate,
            ) {
                return Output {
                    verdict: Verdict::Sat,
                    proof: None,
                    skolem: Some(sk),
                    stats: format!("expand (slice {:.2}s)", slice),
                };
            }
            if unsat_row.is_some() {
                known_unsat = true;
            }
        }

        // ---- Saturate slice ----
        let now = start.elapsed().as_secs_f64();
        let sat_slice = if known_unsat {
            // We already know UNSAT; spend the rest of the budget on a
            // .frp, capped so we still return promptly.
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
        for c in &db.clauses[fed_upto..] {
            if c.len() <= 4 {
                cdcl.add_external(c);
            }
        }
        fed_upto = db.clauses.len();

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
                proof: Some(std::mem::take(&mut db.proof)),
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
            if let Some((part, fr)) = crate::rules::choose_fork(g, &c) {
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
