//! Given-clause saturation with proof recording.

use crate::aiger::Skolem;
use crate::formula::{var, Clause, Formula, Var};
use crate::proof::{Proof, Step};
use crate::rules::{find_information_fork, fork_extend, is_tautology, resolve, universal_reduce};
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
}
impl Default for Config {
    fn default() -> Self {
        Self {
            max_clauses: 200_000,
            max_forks: 256,
            timeout_s: 10.0,
            extract_cert: true,
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
        self.queue.push(Reverse((c.len(), ci)));
        self.clauses.push(c.clone());
        self.backward_subsume(&c, csig, ci);
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

    // Phase 0: greedy universal expansion (SAT-only, cert-producing).
    if cfg.extract_cert {
        if let Some(sk) = crate::expand::try_expand(f) {
            return Output {
                verdict: Verdict::Sat,
                proof: None,
                skolem: Some(sk),
                stats: "expand".into(),
            };
        }
    }

    let mut g = f.clone();
    let mut db = Db::new();

    for c in &g.clauses {
        if is_tautology(c) {
            continue;
        }
        let ai = db.record(c, Step::axiom(c));
        let rc = universal_reduce(&g, c);
        if rc != *c {
            db.record(
                &rc,
                Step {
                    clause: rc.clone(),
                    rule: "ured",
                    premises: vec![ai],
                    pivot: None,
                    part: None,
                    c3: None,
                    fresh: None,
                },
            );
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

    let mut forks = 0usize;
    loop {
        let mut found_empty = false;
        while let Some(Reverse((_, cursor))) = db.queue.pop() {
            if start.elapsed().as_secs_f64() > cfg.timeout_s || db.clauses.len() > cfg.max_clauses {
                return unknown(&db, forks);
            }
            if db.dead[cursor] || db.processed[cursor] {
                continue;
            }
            db.processed[cursor] = true;
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
                    if let Some(r) = resolve(&c, &db.clauses[di], var(l)) {
                        let rr = universal_reduce(&g, &r);
                        if db.seen.contains(&rr) {
                            continue;
                        }
                        let dpi = db.idx[&db.clauses[di]];
                        let step = Step {
                            clause: rr.clone(),
                            rule: "res",
                            premises: vec![ci, dpi],
                            pivot: Some(var(l)),
                            part: None,
                            c3: None,
                            fresh: None,
                        };
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
            return Output {
                verdict: Verdict::Unsat,
                proof: Some(db.proof),
                skolem: None,
                stats: format!("⊥ after {} clauses, {} forks", db.clauses.len(), forks),
            };
        }
        if start.elapsed().as_secs_f64() > cfg.timeout_s || db.clauses.len() > cfg.max_clauses {
            return unknown(&db, forks);
        }
        // saturated; try a fork
        let mut order: Vec<usize> = (0..db.clauses.len()).filter(|&i| !db.dead[i]).collect();
        order.sort_by_key(|&i| db.clauses[i].len());
        let mut forked = false;
        for &i in &order {
            let c = db.clauses[i].clone();
            if let Some((a, _b)) = find_information_fork(&g, &c) {
                let da = g.deps[&a].clone();
                let part: Clause = c
                    .iter()
                    .copied()
                    .filter(|&l| {
                        let v = var(l);
                        v == a || g.dep(v).is_subset(&da)
                    })
                    .collect();
                let src = db.idx[&c];
                let fr = fork_extend(&mut g, &c, &part);
                let part_v = part.clone();
                for (cl, _half) in [(&fr.left, "l"), (&fr.right, "r")] {
                    db.record(
                        cl,
                        Step {
                            clause: cl.clone(),
                            rule: "fex",
                            premises: vec![src],
                            pivot: None,
                            part: Some(part_v.clone()),
                            c3: None,
                            fresh: Some(fr.fresh),
                        },
                    );
                    let rcl = universal_reduce(&g, cl);
                    if rcl != *cl {
                        let pi = db.idx[cl];
                        db.record(
                            &rcl,
                            Step {
                                clause: rcl.clone(),
                                rule: "ured",
                                premises: vec![pi],
                                pivot: None,
                                part: None,
                                c3: None,
                                fresh: None,
                            },
                        );
                    }
                    db.activate(rcl);
                }
                forks += 1;
                forked = true;
                break;
            }
        }
        if !forked {
            let sk = if cfg.extract_cert {
                find_skolem_brute(f, &start, cfg.timeout_s)
            } else {
                None
            };
            return Output {
                verdict: Verdict::Sat,
                proof: None,
                skolem: sk,
                stats: format!("saturated: {} clauses", db.clauses.len()),
            };
        }
        if forks >= cfg.max_forks {
            return unknown(&db, forks);
        }
    }
}

fn unknown(db: &Db, forks: usize) -> Output {
    Output {
        verdict: Verdict::Unknown,
        proof: None,
        skolem: None,
        stats: format!("budget: {} clauses, {} forks", db.clauses.len(), forks),
    }
}

fn find_skolem_brute(f: &Formula, start: &Instant, deadline: f64) -> Option<Skolem> {
    let exs: Vec<Var> = f.deps.keys().copied().collect();
    let dep_lists: Vec<Vec<Var>> = exs
        .iter()
        .map(|y| f.deps[y].iter().copied().collect())
        .collect();
    let dom_sizes: Vec<usize> = dep_lists.iter().map(|d| 1usize << d.len()).collect();
    let total_bits: usize = dom_sizes.iter().sum();
    if total_bits > 20 {
        return None;
    }
    let total: u64 = 1u64 << total_bits;
    let mut tables: Vec<Vec<bool>> = dom_sizes.iter().map(|&s| vec![false; s]).collect();
    for counter in 0..total {
        if counter & 0x3ff == 0 && start.elapsed().as_secs_f64() > deadline {
            return None;
        }
        // unpack counter into tables
        let mut bits = counter;
        for (i, t) in tables.iter_mut().enumerate() {
            for b in t.iter_mut() {
                *b = bits & 1 == 1;
                bits >>= 1;
            }
            let _ = i;
        }
        if check_model(f, &exs, &dep_lists, &tables) {
            let mut sk = Skolem::new();
            for (i, &y) in exs.iter().enumerate() {
                let nd = dep_lists[i].len();
                let mut bits = vec![0u64; ((1usize << nd) + 63) / 64];
                for (j, &v) in tables[i].iter().enumerate() {
                    if v {
                        bits[j / 64] |= 1u64 << (j % 64);
                    }
                }
                sk.insert(y, (bits, nd));
            }
            return Some(sk);
        }
    }
    None
}

fn check_model(f: &Formula, exs: &[Var], deps: &[Vec<Var>], tables: &[Vec<bool>]) -> bool {
    let nu = f.universals.len();
    let mut asg = vec![false; f.n_vars as usize + 1];
    for ub in 0..(1u64 << nu) {
        for (i, &u) in f.universals.iter().enumerate() {
            asg[u as usize] = (ub >> i) & 1 == 1;
        }
        for (i, &y) in exs.iter().enumerate() {
            let mut k = 0usize;
            for (b, d) in deps[i].iter().enumerate() {
                if asg[*d as usize] {
                    k |= 1 << b;
                }
            }
            asg[y as usize] = tables[i][k];
        }
        for c in &f.clauses {
            let mut ok = false;
            for &l in c {
                let v = var(l);
                if (l > 0) == asg[v as usize] {
                    ok = true;
                    break;
                }
            }
            if !ok {
                return false;
            }
        }
    }
    true
}
