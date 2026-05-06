//! Minimal CDCL: two-watched-literals, 1-UIP, assumption-based
//! incremental solving (minisat-style). Learned clauses, watches and
//! per-var state persist across `solve()` calls so the solver can be
//! built once per formula and called once per universal-assignment row.
//!
//! Reference: minisat `Solver::propagate`/`analyze`/`search`; satch's
//! comments for the watch-relink invariants.

use crate::formula::{var, Lit};
use std::collections::HashMap;

/// Internal lit encoding: 2*v for +v, 2*v+1 for -v. Index 0/1 unused.
type ILit = u32;

#[inline]
fn ilit(l: Lit) -> ILit {
    let v = var(l);
    2 * v + if l < 0 { 1 } else { 0 }
}
#[inline]
fn neg(l: ILit) -> ILit {
    l ^ 1
}
#[inline]
fn ivar(l: ILit) -> usize {
    (l >> 1) as usize
}
#[inline]
fn isign(l: ILit) -> i8 {
    if l & 1 == 0 {
        1
    } else {
        -1
    }
}

#[derive(Clone, Copy)]
struct Watcher {
    cref: u32,
    blocker: ILit,
}

const UNDEF: u32 = u32::MAX;

/// Per-clause resolution antecedent: chain[0] is the seed conflict
/// clause (pivot = 0); each subsequent (cref, pivot) resolves the
/// running resolvent against `cref` on variable `pivot`. Replaying the
/// chain yields the learned clause exactly (level-0 lits included).
type Chain = Vec<(u32, u32)>;

#[derive(Default)]
pub struct ProofLog {
    pub n_input: usize,
    /// learned cref → chain that derives it.
    pub ante: HashMap<u32, Chain>,
    /// Chain deriving the final assumption-only clause (or ⊥).
    pub final_chain: Chain,
    /// The clause `final_chain` derives — every lit is an assumption.
    pub final_clause: Vec<Lit>,
}

pub struct Cdcl {
    /// Flat clause storage: each clause is [len, lit0, lit1, ...].
    arena: Vec<u32>,
    crefs: Vec<u32>, // start indices into arena (for iteration / reason lookup)
    watches: Vec<Vec<Watcher>>, // indexed by ILit
    value: Vec<i8>,  // -1/0/1 per var
    level: Vec<u32>,
    reason: Vec<u32>, // cref or UNDEF
    seen: Vec<u8>,
    trail: Vec<ILit>,
    trail_lim: Vec<usize>,
    qhead: usize,
    n_vars: usize,
    ok: bool,
    phase: Vec<i8>, // saved last-polarity per var
    activity: Vec<f64>,
    var_inc: f64,
    pub conflicts: u64,
    pub n_learned: usize,
    pub budget_hit: bool,
    decide: Vec<bool>,
    core: Vec<Lit>,
    pub proof: Option<ProofLog>,
    /// First unit-vs-unit conflict detected during clause loading, before
    /// proof logging is enabled. `enable_proof_log` re-seats it as a cref
    /// so `solve()` can emit a chain instead of a bare `ok=false`.
    init_unit_conflict: ILit,
}

impl Cdcl {
    pub fn new(n_vars: usize, clauses: &[Vec<Lit>]) -> Self {
        let mut s = Self {
            arena: Vec::new(),
            crefs: Vec::new(),
            watches: vec![Vec::new(); 2 * (n_vars + 1)],
            value: vec![0i8; n_vars + 1],
            level: vec![0u32; n_vars + 1],
            reason: vec![UNDEF; n_vars + 1],
            seen: vec![0u8; n_vars + 1],
            trail: Vec::new(),
            trail_lim: Vec::new(),
            qhead: 0,
            n_vars,
            ok: true,
            phase: vec![1i8; n_vars + 1],
            activity: vec![0.0; n_vars + 1],
            var_inc: 1.0,
            conflicts: 0,
            n_learned: 0,
            budget_hit: false,
            decide: vec![true; n_vars + 1],
            core: Vec::new(),
            proof: None,
            init_unit_conflict: 0,
        };
        for c in clauses {
            let lits: Vec<ILit> = c.iter().map(|&l| ilit(l)).collect();
            s.add_clause(&lits, false);
        }
        s
    }

    pub fn enable_proof_log(&mut self) {
        // `new()` ran with proof=None, so input units took the v1.20
        // fast path (reason=UNDEF, no cref). Re-seat them now so chains
        // can reference them as axioms.
        for i in 0..self.trail.len() {
            let l = self.trail[i];
            let v = ivar(l);
            if self.reason[v] == UNDEF && self.level[v] == 0 {
                let cr = self.arena.len() as u32;
                self.arena.push(1);
                self.arena.push(l);
                self.crefs.push(cr);
                self.reason[v] = cr;
            }
        }
        let mut pl = ProofLog {
            n_input: self.crefs.len(),
            ..Default::default()
        };
        if !self.ok && self.init_unit_conflict != 0 {
            let cr = self.arena.len() as u32;
            self.arena.push(1);
            self.arena.push(self.init_unit_conflict);
            self.crefs.push(cr);
            pl.n_input = self.crefs.len();
            self.proof = Some(pl);
            let (fc, ch) = self.extract_unsat_chain(cr);
            let p = self.proof.as_mut().unwrap();
            p.final_clause = fc;
            p.final_chain = ch;
            return;
        }
        self.proof = Some(pl);
    }

    pub fn clause_lits(&self, cr: u32) -> Vec<Lit> {
        (0..self.cl_len(cr))
            .map(|k| {
                let l = self.cl_lit(cr, k);
                if isign(l) > 0 {
                    ivar(l) as Lit
                } else {
                    -(ivar(l) as Lit)
                }
            })
            .collect()
    }

    pub fn is_input(&self, cr: u32) -> bool {
        self.proof
            .as_ref()
            .map(|p| {
                self.crefs
                    .iter()
                    .position(|&c| c == cr)
                    .map_or(false, |i| i < p.n_input)
            })
            .unwrap_or(false)
    }

    fn cl_len(&self, cr: u32) -> u32 {
        self.arena[cr as usize]
    }
    fn cl_lit(&self, cr: u32, i: u32) -> ILit {
        self.arena[cr as usize + 1 + i as usize]
    }
    fn cl_set(&mut self, cr: u32, i: u32, l: ILit) {
        self.arena[cr as usize + 1 + i as usize] = l;
    }

    fn add_clause(&mut self, lits: &[ILit], learned: bool) -> u32 {
        if lits.is_empty() {
            self.ok = false;
            return UNDEF;
        }
        // Units only need a cref when proof-logging (so chains can
        // reference them as axioms). Without logging, v1.20's behaviour
        // — enqueue with reason=UNDEF and skip the arena — keeps the
        // many-row arbiter CDCLs at v1.20 speed.
        if lits.len() == 1 && self.proof.is_none() {
            match self.val_lit(lits[0]) {
                0 => self.enqueue(lits[0], UNDEF),
                -1 => {
                    if self.init_unit_conflict == 0 {
                        self.init_unit_conflict = lits[0];
                    }
                    self.ok = false;
                }
                _ => {}
            }
            return UNDEF;
        }
        let cr = self.arena.len() as u32;
        self.arena.push(lits.len() as u32);
        self.arena.extend_from_slice(lits);
        self.crefs.push(cr);
        if learned {
            self.n_learned += 1;
        }
        if lits.len() == 1 {
            match self.val_lit(lits[0]) {
                0 => self.enqueue(lits[0], cr),
                -1 => self.ok = false,
                _ => {}
            }
            return cr;
        }
        self.watches[neg(lits[0]) as usize].push(Watcher {
            cref: cr,
            blocker: lits[1],
        });
        self.watches[neg(lits[1]) as usize].push(Watcher {
            cref: cr,
            blocker: lits[0],
        });
        cr
    }

    #[inline]
    fn val_lit(&self, l: ILit) -> i8 {
        let v = self.value[ivar(l)];
        if v == 0 {
            0
        } else if isign(l) == v {
            1
        } else {
            -1
        }
    }

    fn enqueue(&mut self, l: ILit, reason: u32) {
        let v = ivar(l);
        debug_assert_eq!(self.value[v], 0);
        self.value[v] = isign(l);
        self.level[v] = self.dl();
        self.reason[v] = reason;
        self.trail.push(l);
    }

    #[inline]
    fn dl(&self) -> u32 {
        self.trail_lim.len() as u32
    }

    pub fn last_core(&self) -> &[Lit] {
        &self.core
    }

    /// Minisat analyzeFinal: subset of assumptions implying ¬p (where p is
    /// the assumption that was found false, passed as ¬a).
    fn analyze_final(&mut self, p: ILit) -> Vec<Lit> {
        // Returned core is a subset of *assumptions* that is unsatisfiable
        // together. `p = ¬a` where `a` is the violated assumption; the
        // walk collects decisions implying p, and `a` itself completes
        // the unsat subset (Minisat includes it; previous version didn't,
        // which made callers that test "is X in core?" miss the violated
        // assumption).
        let a = neg(p);
        let mut out: Vec<Lit> = vec![if isign(a) > 0 {
            ivar(a) as Lit
        } else {
            -(ivar(a) as Lit)
        }];
        if self.dl() == 0 {
            return out;
        }
        self.seen[ivar(p)] = 1;
        let mut to_clear = vec![ivar(p)];
        for &l in self.trail.iter().rev() {
            let v = ivar(l);
            if self.seen[v] == 0 {
                continue;
            }
            if self.reason[v] == UNDEF {
                debug_assert!(self.level[v] > 0);
                out.push(if isign(l) > 0 { v as Lit } else { -(v as Lit) });
            } else {
                let cr = self.reason[v];
                let len = self.cl_len(cr);
                for k in 1..len {
                    let q = self.cl_lit(cr, k);
                    if self.level[ivar(q)] > 0 {
                        self.seen[ivar(q)] = 1;
                        to_clear.push(ivar(q));
                    }
                }
            }
        }
        for v in to_clear {
            self.seen[v] = 0;
        }
        out
    }

    fn cancel_until(&mut self, lvl: u32) {
        if self.dl() <= lvl {
            return;
        }
        let lim = self.trail_lim[lvl as usize];
        for &l in &self.trail[lim..] {
            let v = ivar(l);
            self.phase[v] = self.value[v];
            self.value[v] = 0;
            self.reason[v] = UNDEF;
        }
        self.trail.truncate(lim);
        self.trail_lim.truncate(lvl as usize);
        self.qhead = self.trail.len();
    }

    /// Returns conflict cref or UNDEF.
    fn propagate(&mut self) -> u32 {
        while self.qhead < self.trail.len() {
            let p = self.trail[self.qhead];
            self.qhead += 1;
            let mut ws = std::mem::take(&mut self.watches[p as usize]);
            let mut j = 0usize;
            let mut i = 0usize;
            while i < ws.len() {
                let w = ws[i];
                i += 1;
                if self.val_lit(w.blocker) == 1 {
                    ws[j] = w;
                    j += 1;
                    continue;
                }
                let cr = w.cref;
                let np = neg(p);
                // Ensure c[1] == ~p.
                if self.cl_lit(cr, 0) == np {
                    let l1 = self.cl_lit(cr, 1);
                    self.cl_set(cr, 0, l1);
                    self.cl_set(cr, 1, np);
                }
                let first = self.cl_lit(cr, 0);
                if first != w.blocker && self.val_lit(first) == 1 {
                    ws[j] = Watcher {
                        cref: cr,
                        blocker: first,
                    };
                    j += 1;
                    continue;
                }
                // Look for a new watch among c[2..].
                let len = self.cl_len(cr);
                let mut found = false;
                for k in 2..len {
                    let lk = self.cl_lit(cr, k);
                    if self.val_lit(lk) != -1 {
                        self.cl_set(cr, 1, lk);
                        self.cl_set(cr, k, np);
                        self.watches[neg(lk) as usize].push(Watcher {
                            cref: cr,
                            blocker: first,
                        });
                        found = true;
                        break;
                    }
                }
                if found {
                    continue; // dropped from this list
                }
                // Keep watch; unit or conflict.
                ws[j] = Watcher {
                    cref: cr,
                    blocker: first,
                };
                j += 1;
                if self.val_lit(first) == -1 {
                    // Conflict: copy remaining and bail.
                    while i < ws.len() {
                        ws[j] = ws[i];
                        i += 1;
                        j += 1;
                    }
                    ws.truncate(j);
                    self.watches[p as usize] = ws;
                    self.qhead = self.trail.len();
                    return cr;
                }
                self.enqueue(first, cr);
            }
            ws.truncate(j);
            self.watches[p as usize] = ws;
        }
        UNDEF
    }

    /// 1-UIP. Returns (learned, backtrack_level, chain).
    fn analyze(&mut self, mut cr: u32) -> (Vec<ILit>, u32, Chain) {
        let logging = self.proof.is_some();
        let mut chain: Chain = if logging { vec![(cr, 0)] } else { Chain::new() };
        let mut lvl0: Vec<usize> = Vec::new();
        let dl = self.dl();
        let mut learned: Vec<ILit> = vec![0]; // hole for asserting lit
        let mut path_c = 0usize;
        let mut idx = self.trail.len();
        let mut p: ILit = u32::MAX;
        let mut to_clear: Vec<usize> = Vec::new();
        loop {
            debug_assert!(cr != UNDEF);
            let start = if p == u32::MAX { 0 } else { 1 };
            let len = self.cl_len(cr);
            for k in start..len {
                let q = self.cl_lit(cr, k);
                let v = ivar(q);
                if self.seen[v] != 0 {
                    continue;
                }
                if self.level[v] == 0 {
                    if logging {
                        self.seen[v] = 1;
                        to_clear.push(v);
                        lvl0.push(v);
                    }
                    continue;
                }
                self.seen[v] = 1;
                to_clear.push(v);
                self.bump(v);
                if self.level[v] == dl {
                    path_c += 1;
                } else {
                    learned.push(q);
                }
            }
            // Next seen on trail at dl.
            loop {
                idx -= 1;
                if self.seen[ivar(self.trail[idx])] != 0
                    && self.level[ivar(self.trail[idx])] == dl
                {
                    break;
                }
            }
            p = self.trail[idx];
            let v = ivar(p);
            self.seen[v] = 0;
            path_c -= 1;
            if path_c == 0 {
                break;
            }
            cr = self.reason[v];
            if logging {
                chain.push((cr, v as u32));
            }
        }
        learned[0] = neg(p);
        // Proof: resolve away every level-0 lit touched. Process in
        // *reverse trail order* so a reason clause (whose other lits
        // are all earlier on the trail) never re-introduces a var we
        // already removed.
        if logging && !lvl0.is_empty() {
            let pos0: HashMap<usize, usize> = self
                .trail
                .iter()
                .enumerate()
                .filter(|&(_, &l)| self.level[ivar(l)] == 0)
                .map(|(i, &l)| (ivar(l), i))
                .collect();
            let mut heap: std::collections::BinaryHeap<(usize, usize)> =
                lvl0.iter().map(|&v| (pos0[&v], v)).collect();
            while let Some((_, v)) = heap.pop() {
                let r = self.reason[v];
                if r == UNDEF {
                    chain.clear();
                    break;
                }
                chain.push((r, v as u32));
                for k in 0..self.cl_len(r) {
                    let qv = ivar(self.cl_lit(r, k));
                    if qv == v || self.seen[qv] != 0 {
                        continue;
                    }
                    debug_assert_eq!(self.level[qv], 0);
                    self.seen[qv] = 1;
                    to_clear.push(qv);
                    heap.push((pos0[&qv], qv));
                }
            }
        }
        // backtrack level + place its lit at learned[1]
        let bt = if learned.len() == 1 {
            0
        } else {
            let mut max_i = 1usize;
            for i in 2..learned.len() {
                if self.level[ivar(learned[i])] > self.level[ivar(learned[max_i])] {
                    max_i = i;
                }
            }
            learned.swap(1, max_i);
            self.level[ivar(learned[1])]
        };
        for v in to_clear {
            self.seen[v] = 0;
        }
        (learned, bt, chain)
    }

    /// After UNSAT detection (before cancel_until): resolve `seed` against
    /// every reason transitively until only assumption/decision lits
    /// (reason==UNDEF) remain. Returns (final_clause, chain).
    fn extract_unsat_chain(&mut self, seed: u32) -> (Vec<Lit>, Chain) {
        let mut chain: Chain = vec![(seed, 0)];
        let mut to_clear: Vec<usize> = Vec::new();
        let mut work: Vec<usize> = Vec::new();
        let mut out: Vec<Lit> = Vec::new();
        for k in 0..self.cl_len(seed) {
            let v = ivar(self.cl_lit(seed, k));
            if self.seen[v] != 0 {
                continue;
            }
            self.seen[v] = 1;
            to_clear.push(v);
            if self.reason[v] == UNDEF {
                out.push(v as Lit);
            } else {
                work.push(v);
            }
        }
        // Reverse-trail order so a reason's earlier-propagated lits
        // never re-introduce a var already removed.
        let pos: HashMap<usize, usize> = self
            .trail
            .iter()
            .enumerate()
            .map(|(i, &l)| (ivar(l), i))
            .collect();
        let mut heap: std::collections::BinaryHeap<(usize, usize)> =
            work.drain(..).map(|v| (pos[&v], v)).collect();
        while let Some((_, v)) = heap.pop() {
            let r = self.reason[v];
            chain.push((r, v as u32));
            for k in 0..self.cl_len(r) {
                let qv = ivar(self.cl_lit(r, k));
                if qv == v || self.seen[qv] != 0 {
                    continue;
                }
                self.seen[qv] = 1;
                to_clear.push(qv);
                if self.reason[qv] == UNDEF {
                    out.push(qv as Lit);
                } else {
                    heap.push((pos[&qv], qv));
                }
            }
        }
        // Assign correct polarity: each out-var v is on trail with some
        // value; in the derived clause it appears negated.
        for l in out.iter_mut() {
            let v = *l as usize;
            *l = if self.value[v] > 0 { -(v as Lit) } else { v as Lit };
        }
        for v in to_clear {
            self.seen[v] = 0;
        }
        (out, chain)
    }

    fn pick_branch(&self, vsids: bool) -> Option<ILit> {
        // Hybrid: first-unset (deterministic) until a conflict happened
        // in this solve; then VSIDS.
        let v = if vsids {
            let mut best: Option<usize> = None;
            let mut best_a = -1.0f64;
            for v in 1..=self.n_vars {
                if self.value[v] == 0 && self.decide[v] && self.activity[v] > best_a {
                    best_a = self.activity[v];
                    best = Some(v);
                }
            }
            best
        } else {
            (1..=self.n_vars).find(|&v| self.value[v] == 0 && self.decide[v])
        };
        v.map(|v| {
            if self.phase[v] >= 0 {
                2 * v as ILit
            } else {
                2 * v as ILit + 1
            }
        })
    }

    pub fn set_decision(&mut self, v: u32, d: bool) {
        if (v as usize) <= self.n_vars {
            self.decide[v as usize] = d;
        }
    }

    /// Incremental solve under `assumptions` (external Lit polarity).
    /// On SAT, fills `model[var]` ∈ {-1,0,1} (0 if don't-care). On
    /// UNSAT-under-assumptions or budget exhausted, returns false.
    pub fn reset_phase(&mut self) {
        for p in self.phase.iter_mut() {
            *p = 1;
        }
    }

    pub fn set_phase(&mut self, v: u32, p: i8) {
        if (v as usize) < self.phase.len() {
            self.phase[v as usize] = p;
        }
    }

    /// Add a clause discovered externally (e.g. by saturation). Must be
    /// matrix-valid. Cancels to level 0 first so watches stay consistent.
    pub fn add_external(&mut self, c: &[Lit]) {
        if !self.ok {
            return;
        }
        self.cancel_until(0);
        // Drop satisfied / shrink falsified at level-0.
        let mut lits: Vec<ILit> = Vec::with_capacity(c.len());
        for &l in c {
            match self.val_lit(ilit(l)) {
                1 => return, // already satisfied
                0 => lits.push(ilit(l)),
                _ => {} // falsified: drop literal
            }
        }
        lits.sort_unstable();
        lits.dedup();
        self.add_clause(&lits, true);
    }

    #[inline]
    fn bump(&mut self, v: usize) {
        self.activity[v] += self.var_inc;
        if self.activity[v] > 1e100 {
            for a in self.activity.iter_mut() {
                *a *= 1e-100;
            }
            self.var_inc *= 1e-100;
        }
    }

    pub fn solve(&mut self, assumptions: &[Lit], model: &mut [i8], max_conflicts: u64) -> bool {
        self.budget_hit = false;
        self.core.clear();
        if !self.ok {
            return false;
        }
        self.cancel_until(0);
        let assumps: Vec<ILit> = assumptions.iter().map(|&l| ilit(l)).collect();
        let start_conflicts = self.conflicts;
        loop {
            let confl = self.propagate();
            if confl != UNDEF {
                self.conflicts += 1;
                self.var_inc /= 0.95;
                if self.dl() == 0 {
                    if self.proof.is_some() {
                        let (fc, ch) = self.extract_unsat_chain(confl);
                        let p = self.proof.as_mut().unwrap();
                        p.final_clause = fc;
                        p.final_chain = ch;
                    }
                    self.ok = false;
                    return false;
                }
                if self.conflicts - start_conflicts > max_conflicts {
                    self.budget_hit = true;
                    self.cancel_until(0);
                    return false;
                }
                let (learned, bt, chain) = self.analyze(confl);
                self.cancel_until(bt);
                let cr = self.add_clause(&learned, true);
                if let Some(p) = self.proof.as_mut() {
                    p.ante.insert(cr, chain);
                }
                if !self.ok {
                    if self.proof.is_some() && cr != UNDEF {
                        let (fc, ch) = self.extract_unsat_chain(cr);
                        let p = self.proof.as_mut().unwrap();
                        p.final_clause = fc;
                        p.final_chain = ch;
                    }
                    return false;
                }
                if learned.len() > 1 {
                    self.enqueue(learned[0], cr);
                }
                continue;
            }
            // No conflict: decide.
            if (self.dl() as usize) < assumps.len() {
                let a = assumps[self.dl() as usize];
                match self.val_lit(a) {
                    1 => self.trail_lim.push(self.trail.len()), // empty level
                    -1 => {
                        // Assumption violated → UNSAT under assumptions.
                        self.core = self.analyze_final(neg(a));
                        if self.proof.is_some() {
                            let r = self.reason[ivar(a)];
                            let (mut fc, ch) = if r == UNDEF {
                                // ¬a is itself an earlier assumption.
                                (vec![], vec![])
                            } else {
                                self.extract_unsat_chain(r)
                            };
                            // The violated assumption appears positively
                            // in the derived clause iff r contained ¬a;
                            // either way, the final clause is over
                            // assumptions only. Ensure ¬a's polarity is
                            // present (resolved seed has ¬a as a lit).
                            if r != UNDEF {
                                let av = ivar(a) as Lit;
                                let want = if isign(a) > 0 { -av } else { av };
                                if !fc.contains(&want) {
                                    fc.push(want);
                                }
                            }
                            let p = self.proof.as_mut().unwrap();
                            p.final_clause = fc;
                            p.final_chain = ch;
                        }
                        self.cancel_until(0);
                        return false;
                    }
                    _ => {
                        self.trail_lim.push(self.trail.len());
                        self.enqueue(a, UNDEF);
                    }
                }
                continue;
            }
            match self.pick_branch(self.conflicts > start_conflicts) {
                None => {
                    // SAT.
                    for v in 1..=self.n_vars {
                        model[v] = self.value[v];
                    }
                    self.cancel_until(0);
                    return true;
                }
                Some(l) => {
                    self.trail_lim.push(self.trail.len());
                    self.enqueue(l, UNDEF);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lits(v: &[i32]) -> Vec<Lit> {
        v.to_vec()
    }

    #[test]
    fn sat_simple() {
        // (a∨b) ∧ (¬a∨b) ∧ (¬b∨c)  → SAT (b,c true)
        let cs = vec![lits(&[1, 2]), lits(&[-1, 2]), lits(&[-2, 3])];
        let mut s = Cdcl::new(3, &cs);
        let mut m = vec![0i8; 4];
        assert!(s.solve(&[], &mut m, 1000));
        assert_eq!(m[2], 1);
        assert_eq!(m[3], 1);
    }

    #[test]
    fn unsat_simple() {
        let cs = vec![lits(&[1]), lits(&[-1])];
        let mut s = Cdcl::new(1, &cs);
        let mut m = vec![0i8; 2];
        assert!(!s.solve(&[], &mut m, 1000));
    }

    #[test]
    fn assumptions() {
        // (a∨b): SAT; under a=false → b forced; under a=false,b=false → UNSAT.
        let cs = vec![lits(&[1, 2])];
        let mut s = Cdcl::new(2, &cs);
        let mut m = vec![0i8; 3];
        assert!(s.solve(&[-1], &mut m, 1000));
        assert_eq!(m[2], 1);
        assert!(!s.solve(&[-1, -2], &mut m, 1000));
        // Learned clauses persist; re-solve without assumptions still SAT.
        assert!(s.solve(&[], &mut m, 1000));
    }

    #[test]
    fn php3() {
        // Pigeonhole 3→2: UNSAT, needs learning.
        let cs = vec![
            lits(&[1, 2]),
            lits(&[3, 4]),
            lits(&[5, 6]),
            lits(&[-1, -3]),
            lits(&[-1, -5]),
            lits(&[-3, -5]),
            lits(&[-2, -4]),
            lits(&[-2, -6]),
            lits(&[-4, -6]),
        ];
        let mut s = Cdcl::new(6, &cs);
        let mut m = vec![0i8; 7];
        assert!(!s.solve(&[], &mut m, 1000));
        assert!(s.conflicts > 0);
    }
}
