//! Naive saturation search with proof recording.

use crate::aiger::Skolem;
use crate::formula::{var, Clause, Formula, Var};
use crate::proof::{Proof, Step};
use crate::rules::{find_information_fork, fork_extend, is_tautology, resolve, universal_reduce};
use std::collections::{BTreeMap, BTreeSet, HashMap};
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
            max_clauses: 50_000,
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

pub fn solve(f: &Formula, cfg: &Config) -> Output {
    let start = Instant::now();
    let deadline = cfg.timeout_s;
    let mut g = f.clone();
    let mut proof = Proof::default();
    let mut idx: HashMap<Clause, usize> = HashMap::new();

    let admit =
        |proof: &mut Proof, idx: &mut HashMap<Clause, usize>, c: &Clause, s: Step| -> usize {
            if let Some(&i) = idx.get(c) {
                return i;
            }
            let i = proof.add(s);
            idx.insert(c.clone(), i);
            i
        };

    let mut clauses: BTreeSet<Clause> = BTreeSet::new();
    for c in &g.clauses {
        if is_tautology(c) {
            continue;
        }
        let ai = admit(&mut proof, &mut idx, c, Step::axiom(c));
        let rc = universal_reduce(&g, c);
        if rc != *c {
            admit(
                &mut proof,
                &mut idx,
                &rc,
                Step {
                    clause: rc.iter().copied().collect(),
                    rule: "ured",
                    premises: vec![ai],
                    pivot: None,
                    part: None,
                    c3: None,
                    fresh: None,
                },
            );
        }
        clauses.insert(rc);
    }
    if clauses.contains(&Clause::new()) {
        return Output {
            verdict: Verdict::Unsat,
            proof: Some(proof),
            skolem: None,
            stats: "empty clause in input".into(),
        };
    }

    let mut forks = 0usize;
    loop {
        let (db, derived_empty) =
            saturate(&g, clauses, &mut proof, &mut idx, cfg, &start, deadline);
        clauses = db;
        if derived_empty {
            return Output {
                verdict: Verdict::Unsat,
                proof: Some(proof),
                skolem: None,
                stats: format!("⊥ after {} clauses, {} forks", clauses.len(), forks),
            };
        }
        if start.elapsed().as_secs_f64() > deadline || clauses.len() > cfg.max_clauses {
            return Output {
                verdict: Verdict::Unknown,
                proof: None,
                skolem: None,
                stats: format!("budget: {} clauses, {} forks", clauses.len(), forks),
            };
        }
        // pick smallest fork clause
        let mut forked = false;
        let mut sorted: Vec<&Clause> = clauses.iter().collect();
        sorted.sort_by_key(|c| (c.len(), c.iter().copied().collect::<Vec<_>>()));
        let mut to_remove: Option<Clause> = None;
        let mut to_add: Vec<Clause> = Vec::new();
        for c in sorted {
            if let Some((a, _b)) = find_information_fork(&g, c) {
                let da = g.deps[&a].clone();
                let part: Clause = c
                    .iter()
                    .copied()
                    .filter(|&l| {
                        let v = var(l);
                        v == a || g.dep(v).is_subset(&da)
                    })
                    .collect();
                let src = idx[c];
                let fr = fork_extend(&mut g, c, &part);
                let part_v: Vec<_> = part.iter().copied().collect();
                admit(
                    &mut proof,
                    &mut idx,
                    &fr.left,
                    Step {
                        clause: fr.left.iter().copied().collect(),
                        rule: "fex",
                        premises: vec![src],
                        pivot: None,
                        part: Some(part_v.clone()),
                        c3: None,
                        fresh: Some(fr.fresh),
                    },
                );
                admit(
                    &mut proof,
                    &mut idx,
                    &fr.right,
                    Step {
                        clause: fr.right.iter().copied().collect(),
                        rule: "fex",
                        premises: vec![src],
                        pivot: None,
                        part: Some(part_v),
                        c3: None,
                        fresh: Some(fr.fresh),
                    },
                );
                to_remove = Some(c.clone());
                for nc in [&fr.left, &fr.right] {
                    let rnc = universal_reduce(&g, nc);
                    if rnc != *nc {
                        let pi = idx[nc];
                        admit(
                            &mut proof,
                            &mut idx,
                            &rnc,
                            Step {
                                clause: rnc.iter().copied().collect(),
                                rule: "ured",
                                premises: vec![pi],
                                pivot: None,
                                part: None,
                                c3: None,
                                fresh: None,
                            },
                        );
                    }
                    to_add.push(rnc);
                }
                forks += 1;
                forked = true;
                break;
            }
        }
        if let Some(r) = to_remove {
            clauses.remove(&r);
        }
        for c in to_add {
            clauses.insert(c);
        }
        if !forked {
            // saturated, no fork — SAT
            let sk = if cfg.extract_cert {
                find_skolem_brute(f, &start, deadline)
            } else {
                None
            };
            return Output {
                verdict: Verdict::Sat,
                proof: None,
                skolem: sk,
                stats: format!("saturated: {} clauses", clauses.len()),
            };
        }
        if forks >= cfg.max_forks {
            return Output {
                verdict: Verdict::Unknown,
                proof: None,
                skolem: None,
                stats: format!("fork budget ({})", forks),
            };
        }
    }
}

fn saturate(
    g: &Formula,
    clauses: BTreeSet<Clause>,
    proof: &mut Proof,
    idx: &mut HashMap<Clause, usize>,
    cfg: &Config,
    start: &Instant,
    deadline: f64,
) -> (BTreeSet<Clause>, bool) {
    let mut db: BTreeSet<Clause> = clauses;
    let mut todo: Vec<Clause> = db.iter().cloned().collect();
    while let Some(c) = todo.pop() {
        if start.elapsed().as_secs_f64() > deadline || db.len() > cfg.max_clauses {
            break;
        }
        let snapshot: Vec<Clause> = db.iter().cloned().collect();
        for d in &snapshot {
            if d == &c {
                continue;
            }
            for &l in &c {
                if !d.contains(&(-l)) {
                    continue;
                }
                if let Some(r) = resolve(&c, d, var(l)) {
                    let rr = universal_reduce(g, &r);
                    if db.contains(&rr) {
                        continue;
                    }
                    let ci = idx[&c];
                    let di = idx[d];
                    let i = proof.add(Step {
                        clause: rr.iter().copied().collect(),
                        rule: "res",
                        premises: vec![ci, di],
                        pivot: Some(var(l)),
                        part: None,
                        c3: None,
                        fresh: None,
                    });
                    idx.insert(rr.clone(), i);
                    if rr.is_empty() {
                        db.insert(rr);
                        return (db, true);
                    }
                    db.insert(rr.clone());
                    todo.push(rr);
                }
            }
        }
    }
    (db, false)
}

/// Brute-force Skolem search (tiny instances only — same as Python ref).
fn find_skolem_brute(f: &Formula, start: &Instant, deadline: f64) -> Option<Skolem> {
    let exs: Vec<Var> = f.deps.keys().copied().collect();
    let dep_lists: Vec<Vec<Var>> = exs
        .iter()
        .map(|y| f.deps[y].iter().copied().collect())
        .collect();
    let dom_sizes: Vec<usize> = dep_lists.iter().map(|d| 1usize << d.len()).collect();
    let total: u128 = dom_sizes.iter().map(|&s| 1u128 << s).product();
    if total > 1_000_000 {
        return None;
    }
    let mut tables: Vec<Vec<bool>> = dom_sizes.iter().map(|&s| vec![false; s]).collect();
    let mut counter: u128 = 0;
    loop {
        if start.elapsed().as_secs_f64() > deadline {
            return None;
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
        counter += 1;
        if counter >= total {
            return None;
        }
        // increment mixed-radix tables
        let mut carry = 1u128;
        for t in tables.iter_mut() {
            if carry == 0 {
                break;
            }
            for b in t.iter_mut() {
                if carry == 0 {
                    break;
                }
                if *b {
                    *b = false;
                } else {
                    *b = true;
                    carry = 0;
                }
            }
        }
    }
}

fn check_model(f: &Formula, exs: &[Var], deps: &[Vec<Var>], tables: &[Vec<bool>]) -> bool {
    let nu = f.universals.len();
    for ub in 0..(1u64 << nu) {
        let mut asg: BTreeMap<Var, bool> = BTreeMap::new();
        for (i, &u) in f.universals.iter().enumerate() {
            asg.insert(u, (ub >> i) & 1 == 1);
        }
        for (i, &y) in exs.iter().enumerate() {
            let mut k = 0usize;
            for (b, d) in deps[i].iter().enumerate() {
                if asg[d] {
                    k |= 1 << b;
                }
            }
            asg.insert(y, tables[i][k]);
        }
        for c in &f.clauses {
            let mut ok = false;
            for &l in c {
                let v = var(l);
                let val = asg.get(&v).copied().unwrap_or(false);
                if (l > 0) == val {
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
