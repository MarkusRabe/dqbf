//! Given-clause saturation with proof recording.

use crate::aiger::Skolem;
use crate::formula::{var, Clause, Formula, Var};
use crate::proof::{Proof, Step};
use crate::rules::{find_information_fork, fork_extend, is_tautology, resolve, universal_reduce};
use std::collections::{BTreeMap, HashMap, HashSet};
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

struct Db {
    clauses: Vec<Clause>,
    seen: HashSet<Clause>,
    proof: Proof,
    idx: HashMap<Clause, usize>,
    occ: HashMap<Lit, Vec<usize>>,
}

impl Db {
    fn new() -> Self {
        Self {
            clauses: Vec::new(),
            seen: HashSet::new(),
            proof: Proof::default(),
            idx: HashMap::new(),
            occ: HashMap::new(),
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
        if self.seen.insert(c.clone()) {
            let ci = self.clauses.len();
            for &l in &c {
                self.occ.entry(l).or_default().push(ci);
            }
            self.clauses.push(c);
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

    let mut cursor = 0usize;
    let mut forks = 0usize;
    loop {
        // given-clause: process db.clauses[cursor..] against db.clauses[0..cursor]
        let mut found_empty = false;
        while cursor < db.clauses.len() {
            if start.elapsed().as_secs_f64() > cfg.timeout_s || db.clauses.len() > cfg.max_clauses {
                return unknown(&db, forks);
            }
            let c = db.clauses[cursor].clone();
            let ci = db.idx[&c];
            'lits: for &l in &c {
                let partners: Vec<usize> = db
                    .occ
                    .get(&(-l))
                    .map(|v| v.iter().copied().filter(|&di| di < cursor).collect())
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
            cursor += 1;
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
        let mut order: Vec<usize> = (0..db.clauses.len()).collect();
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
                let mut tbl = BTreeMap::new();
                for (j, &v) in tables[i].iter().enumerate() {
                    let key: Vec<bool> =
                        (0..dep_lists[i].len()).map(|b| (j >> b) & 1 == 1).collect();
                    tbl.insert(key, v);
                }
                sk.insert(y, tbl);
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
