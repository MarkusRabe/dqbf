//! Resumable expand: holds free-pass / slot-DPLL / outer-CEGAR state
//! across slices so the interleaved scheduler can yield mid-search and
//! resume without redoing work.

use crate::aiger::Skolem;
use crate::cdcl::Cdcl;
use crate::expand::{build_skolem, deepening_partial_scan, extract, rank_universals, MAX_U};
use crate::formula::{Clause, Formula, Lit, Var};
use std::collections::{HashMap, HashSet};

macro_rules! dbg_ex {
    ($d:expr, $($a:tt)*) => { if $d { eprintln!("c [expand] {}", format!($($a)*)); } }
}

pub enum Step {
    Sat(Option<Skolem>),
    UnsatRow(u32),
    Unsat,   // exhausted slot space; no Skolem exists; no cert
    Pending, // ran out of slice budget mid-search
    Done,    // exhausted; can't decide
}

enum Mode {
    Definability,
    Partial,
    OuterCegar,
    SlotDpll,
    Exhausted,
}

pub struct ExpandState {
    // Immutable per-formula
    exs: Vec<Var>,
    dep_lists: Vec<Vec<Var>>,
    dep_mask: Vec<u32>,
    expand_us: Vec<Var>,
    rows: u32,
    row_budget: u64,
    n: usize,
    bce_stack: Vec<(Clause, Lit)>,
    mode: Mode,

    // Free-pass state (resumable)
    free_row: u32,
    first_seen: Vec<Vec<i8>>,
    slots: Vec<(usize, usize)>,
    in_slot: HashSet<(usize, usize)>,

    // Slot-DPLL state
    slot_val: Vec<i8>,
    decisions: Vec<(usize, bool)>,
    next_slot: usize,
    cegar_round: usize,
    new_conflicts: HashSet<(usize, usize)>,
    batch: bool,

    // Outer-CEGAR state
    outer: Vec<usize>,
    outer_learned: Vec<Vec<Lit>>,
    outer_pins: Vec<(Var, i8)>,
    bad_rows: Vec<u32>,

    // Definability-CEGAR persisted state (built lazily; resumes
    // across slices instead of rebuilding three CDCL instances).
    cegar: Option<crate::arbiter::CegarState>,

    // Scratch
    tables: Vec<Vec<i8>>,
    model: Vec<i8>,
}

impl ExpandState {
    pub fn new(f: &Formula, bce_stack: Vec<(Clause, Lit)>) -> Self {
        let nu_full = f.universals.len();
        let eae_full = f.deps.values().all(|d| d.is_empty() || d.len() == nu_full);
        let expand_us = if nu_full <= 16 || (nu_full <= MAX_U && eae_full) {
            f.universals.clone()
        } else {
            let mut us = rank_universals(f);
            us.truncate(16);
            us.sort_unstable();
            us
        };
        let nu = expand_us.len();
        let partial = nu < nu_full;
        let exs: Vec<Var> = f.deps.keys().copied().collect();
        let u_idx: HashMap<Var, usize> =
            expand_us.iter().enumerate().map(|(i, &u)| (u, i)).collect();
        let dep_lists: Vec<Vec<Var>> = exs
            .iter()
            .map(|y| {
                f.deps[y]
                    .iter()
                    .copied()
                    .filter(|d| u_idx.contains_key(d))
                    .collect()
            })
            .collect();
        let dep_mask: Vec<u32> = dep_lists
            .iter()
            .map(|ds| ds.iter().map(|d| 1u32 << u_idx[d]).sum())
            .collect();
        let rows = 1u32 << nu;
        let full_mask = rows.wrapping_sub(1);
        let outer: Vec<usize> = (0..exs.len())
            .filter(|&i| f.deps[&exs[i]].is_empty())
            .collect();
        let eae = dep_mask.iter().all(|&m| m == 0 || m == full_mask);
        // Definability runs first whenever there are ≥2 distinct dep
        // sizes — covers partial (|U|>16) AND consistency-shape
        // (|U|≤16 with multiple keys, where SlotDpll often loops).
        let multi_key = !eae;
        let mode = if partial || multi_key {
            Mode::Definability
        } else if nu > 16 && eae && !outer.is_empty() {
            Mode::OuterCegar
        } else {
            Mode::SlotDpll
        };
        let n = f.n_vars as usize + 1;
        let outer_pins: Vec<(Var, i8)> = outer.iter().map(|&i| (exs[i], -1i8)).collect();
        Self {
            first_seen: (0..exs.len())
                .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
                .collect(),
            tables: (0..exs.len())
                .map(|i| vec![0i8; 1usize << dep_lists[i].len()])
                .collect(),
            exs,
            dep_lists,
            dep_mask,
            expand_us,
            rows,
            row_budget: ((1_000_000 / rows.max(1)) as u64).max(100),
            n,
            bce_stack,
            mode,
            free_row: 0,
            slots: Vec::new(),
            in_slot: HashSet::new(),
            slot_val: Vec::new(),
            decisions: Vec::new(),
            next_slot: 0,
            cegar_round: 0,
            new_conflicts: HashSet::new(),
            batch: rows > (1 << 16),
            outer,
            outer_learned: Vec::new(),
            outer_pins,
            bad_rows: Vec::new(),
            cegar: None,
            model: vec![0i8; n],
        }
    }

    fn row_assumps(&self, ub: u32, extra: &[(Var, i8)]) -> Vec<Lit> {
        let mut a: Vec<Lit> = self
            .expand_us
            .iter()
            .enumerate()
            .map(|(i, &u)| {
                if (ub >> i) & 1 == 1 {
                    u as Lit
                } else {
                    -(u as Lit)
                }
            })
            .collect();
        for &(y, v) in extra {
            if v != 0 {
                a.push(if v > 0 { y as Lit } else { -(y as Lit) });
            }
        }
        a
    }

    pub fn step(
        &mut self,
        f: &Formula,
        cdcl: &mut Cdcl,
        deadline: f64,
        start: &std::time::Instant,
        debug: bool,
    ) -> Step {
        match self.mode {
            Mode::Definability => self.step_definability(f, cdcl, deadline, start, debug),
            Mode::Partial => self.step_partial(f, cdcl, deadline, start, debug),
            Mode::OuterCegar => self.step_outer_cegar(f, cdcl, deadline, start, debug),
            Mode::SlotDpll => self.step_slot_dpll(f, cdcl, deadline, start, debug),
            Mode::Exhausted => Step::Done,
        }
    }

    fn step_definability(
        &mut self,
        f: &Formula,
        cdcl: &mut Cdcl,
        deadline: f64,
        start: &std::time::Instant,
        debug: bool,
    ) -> Step {
        // Budget: at most half the slice for Padoa+CEGAR; the rest
        // falls through to Partial if this doesn't pan out.
        let now = start.elapsed().as_secs_f64();
        let sub_deadline = now + (deadline - now) * 0.7;
        // Gate: definability is for circuit-like matrices. Large
        // unrolled instances (collatz n64, hwmcc) burn budget here for
        // nothing and miss the Partial-mode UNSAT they'd otherwise hit.
        let nu_full = f.universals.len();
        if f.deps.len() > 5000 {
            dbg_ex!(debug, "definability: |E|={} >5000, skip", f.deps.len());
            self.mode = if nu_full > self.expand_us.len() {
                Mode::Partial
            } else {
                Mode::SlotDpll
            };
            return self.step(f, cdcl, deadline, start, debug);
        }
        // Build CegarState once (Padoa + 3×CDCL); subsequent slices
        // resume the same instance.
        if self.cegar.is_none() {
            let padoa_dl = now + (deadline - now) * 0.2;
            dbg_ex!(debug, "definability: padoa→{:.2}s", padoa_dl);
            match crate::definability::padoa_split(f, padoa_dl, start, debug) {
                Some(s) => {
                    dbg_ex!(
                        debug,
                        "padoa: {} defined, {} undefined",
                        s.defined.len(),
                        s.undefined.len()
                    );
                    self.cegar = Some(crate::arbiter::CegarState::new(f, &s.undefined));
                }
                None => {
                    self.mode = if nu_full > self.expand_us.len() {
                        Mode::Partial
                    } else {
                        Mode::SlotDpll
                    };
                    return self.step(f, cdcl, deadline, start, debug);
                }
            }
        }
        use crate::arbiter::CegarOut;
        let cs = self.cegar.as_mut().unwrap();
        match crate::arbiter::validity_cegar(cs, f, sub_deadline, start, debug) {
            CegarOut::Sat(cert) => {
                self.mode = Mode::Exhausted;
                let mut sk = crate::arbiter::forcing_to_skolem(f, &cert, 20).unwrap();
                crate::bce::reconstruct(&mut sk, f, &self.bce_stack);
                Step::Sat(Some(sk))
            }
            CegarOut::Unsat => {
                self.mode = Mode::Exhausted;
                Step::Unsat
            }
            CegarOut::Pending => Step::Pending,
            CegarOut::Bail => {
                self.mode = if nu_full > self.expand_us.len() {
                    Mode::Partial
                } else {
                    Mode::SlotDpll
                };
                self.step(f, cdcl, deadline, start, debug)
            }
        }
    }

    fn step_partial(
        &mut self,
        f: &Formula,
        cdcl: &mut Cdcl,
        deadline: f64,
        start: &std::time::Instant,
        debug: bool,
    ) -> Step {
        if let Some(ub) = deepening_partial_scan(f, cdcl, &mut self.model, deadline, start, debug) {
            self.mode = Mode::Exhausted;
            return Step::UnsatRow(ub);
        }
        // Deepening reached its level cap or deadline; not resumable in
        // its current form (each call restarts at k=8, but CDCL learned
        // clauses persist so it's cheaper).
        if start.elapsed().as_secs_f64() < deadline {
            self.mode = Mode::Exhausted;
            return Step::Done;
        }
        Step::Pending
    }

    fn step_slot_dpll(
        &mut self,
        f: &Formula,
        cdcl: &mut Cdcl,
        deadline: f64,
        start: &std::time::Instant,
        debug: bool,
    ) -> Step {
        // ---- Free pass (resumable from self.free_row) ----
        while self.free_row < self.rows {
            if start.elapsed().as_secs_f64() > deadline {
                return Step::Pending;
            }
            let ub = self.free_row;
            cdcl.reset_phase();
            let assumps = self.row_assumps(ub, &[]);
            if !cdcl.solve(&assumps, &mut self.model, self.row_budget) {
                if !cdcl.budget_hit {
                    self.mode = Mode::Exhausted;
                    return Step::UnsatRow(ub);
                }
                self.mode = Mode::Exhausted;
                return Step::Done;
            }
            for (i, &y) in self.exs.iter().enumerate() {
                let key = extract(ub, self.dep_mask[i]) as usize;
                let v: i8 = if self.model[y as usize] > 0 { 1 } else { -1 };
                if self.first_seen[i][key] == 0 {
                    self.first_seen[i][key] = v;
                } else if self.first_seen[i][key] != v && self.in_slot.insert((i, key)) {
                    self.slots.push((i, key));
                }
            }
            self.free_row += 1;
        }
        if self.slot_val.is_empty() && !self.slots.is_empty() {
            dbg_ex!(debug, "free pass done; {} slots", self.slots.len());
            self.slot_val = vec![0; self.slots.len()];
        }
        if self.slots.is_empty() {
            let mut sk = build_skolem(&self.exs, &self.dep_lists, &self.first_seen);
            crate::bce::reconstruct(&mut sk, f, &self.bce_stack);
            self.mode = Mode::Exhausted;
            return Step::Sat(Some(sk));
        }

        // ---- Slot-DPLL (resumable from self.decisions/next_slot) ----
        let mut pins: Vec<(Var, i8)> = Vec::new();
        let mut iters = 0u64;
        let mut any_budget = false;
        loop {
            iters += 1;
            if iters & 0x3f == 0 && start.elapsed().as_secs_f64() > deadline {
                return Step::Pending;
            }
            while self.next_slot < self.slots.len() {
                let (i, k) = self.slots[self.next_slot];
                self.slot_val[self.next_slot] = self.first_seen[i][k];
                self.decisions.push((self.next_slot, false));
                self.next_slot += 1;
                if !self.batch {
                    break;
                }
            }
            let all_decided = self.next_slot >= self.slots.len();
            for t in self.tables.iter_mut() {
                t.fill(0);
            }
            for (p, &(i, k)) in self.slots.iter().enumerate() {
                self.tables[i][k] = self.slot_val[p];
            }
            let mut prune = false;
            let mut soft = false;
            for ub in 0..self.rows {
                if self.batch && ub & 0x3fff == 0 && start.elapsed().as_secs_f64() > deadline {
                    return Step::Pending;
                }
                pins.clear();
                for (p, &(i, k)) in self.slots.iter().enumerate() {
                    if self.slot_val[p] != 0 && extract(ub, self.dep_mask[i]) as usize == k {
                        pins.push((self.exs[i], self.slot_val[p]));
                    }
                }
                if !self.batch {
                    cdcl.reset_phase();
                }
                let assumps = self.row_assumps(ub, &pins);
                if !cdcl.solve(&assumps, &mut self.model, self.row_budget) {
                    any_budget |= cdcl.budget_hit;
                    prune = true;
                    break;
                }
                for (i, &y) in self.exs.iter().enumerate() {
                    let key = extract(ub, self.dep_mask[i]) as usize;
                    let v: i8 = if self.model[y as usize] > 0 { 1 } else { -1 };
                    if self.tables[i][key] == 0 {
                        self.tables[i][key] = v;
                    } else if self.tables[i][key] != v {
                        soft = true;
                        self.new_conflicts.insert((i, key));
                    }
                }
            }
            if !prune && !soft {
                dbg_ex!(
                    debug,
                    "slot-DPLL SAT r{}: {} slots, {} iters",
                    self.cegar_round,
                    self.slots.len(),
                    iters
                );
                let mut sk = build_skolem(&self.exs, &self.dep_lists, &self.tables);
                crate::bce::reconstruct(&mut sk, f, &self.bce_stack);
                self.mode = Mode::Exhausted;
                return Step::Sat(Some(sk));
            }
            if !prune && !all_decided {
                continue;
            }
            // Backtrack
            loop {
                let (si, flipped) = match self.decisions.pop() {
                    Some(d) => d,
                    None => {
                        let added: Vec<_> = self
                            .new_conflicts
                            .iter()
                            .filter(|s| !self.in_slot.contains(s))
                            .copied()
                            .collect();
                        self.cegar_round += 1;
                        dbg_ex!(
                            debug,
                            "slot-DPLL exhausted r{}: {} slots, {} iters, +{} conflicts, cdcl {}l",
                            self.cegar_round,
                            self.slots.len(),
                            iters,
                            added.len(),
                            cdcl.n_learned
                        );
                        if added.is_empty() {
                            // Every assignment to the current slots was
                            // backtracked: prune (row-UNSAT under pins)
                            // proves that slot-assignment can't extend
                            // to a Skolem table; soft-at-all-decided is
                            // impossible since every slot is pinned.
                            // Exhaustion ⇒ DQBF UNSAT, *unless* some
                            // CDCL call hit its conflict budget (then
                            // the prune was inconclusive).
                            self.mode = Mode::Exhausted;
                            return if any_budget { Step::Done } else { Step::Unsat };
                        }
                        if self.cegar_round >= 50 {
                            self.mode = Mode::Exhausted;
                            return Step::Done;
                        }
                        for s in added {
                            self.slots.push(s);
                            self.in_slot.insert(s);
                        }
                        self.slot_val = vec![0; self.slots.len()];
                        self.next_slot = 0;
                        self.new_conflicts.clear();
                        break;
                    }
                };
                if !flipped {
                    self.slot_val[si] = -self.slot_val[si];
                    self.decisions.push((si, true));
                    self.next_slot = si + 1;
                    for j in self.next_slot..self.slots.len() {
                        self.slot_val[j] = 0;
                    }
                    break;
                }
                self.slot_val[si] = 0;
            }
        }
    }

    fn step_outer_cegar(
        &mut self,
        f: &Formula,
        cdcl: &mut Cdcl,
        deadline: f64,
        start: &std::time::Instant,
        debug: bool,
    ) -> Step {
        let no = self.outer.len();
        let mut pmodel = vec![0i8; no + 1];
        loop {
            if start.elapsed().as_secs_f64() > deadline {
                return Step::Pending;
            }
            // Pick outer values via a tiny CDCL over learned blocking clauses.
            let mut picker = Cdcl::new(no, &self.outer_learned);
            for (j, &(_, v)) in self.outer_pins.iter().enumerate() {
                picker.set_phase((j + 1) as u32, v);
            }
            if !picker.solve(&[], &mut pmodel, 100_000) {
                // Outer-CDCL UNSAT → no constant assignment works.
                self.mode = Mode::Exhausted;
                // We don't have a specific row; signal UNSAT via row 0.
                return Step::UnsatRow(0);
            }
            for (j, &i) in self.outer.iter().enumerate() {
                self.outer_pins[j] = (self.exs[i], if pmodel[j + 1] > 0 { 1 } else { -1 });
            }
            for t in self.tables.iter_mut() {
                t.fill(0);
            }
            // Scan rows: bad-row history first (no table fill — these are
            // re-solved in the full scan to get table entries).
            let mut bad_ub: Option<u32> = None;
            let history: Vec<u32> = self.bad_rows.iter().rev().take(32).copied().collect();
            for ub in history {
                let assumps = self.row_assumps(ub, &self.outer_pins);
                if !cdcl.solve(&assumps, &mut self.model, self.row_budget) && !cdcl.budget_hit {
                    bad_ub = Some(ub);
                    break;
                }
            }
            if bad_ub.is_none() {
                for ub in 0..self.rows {
                    if ub & 0x3fff == 0 && start.elapsed().as_secs_f64() > deadline {
                        return Step::Pending;
                    }
                    let assumps = self.row_assumps(ub, &self.outer_pins);
                    if !cdcl.solve(&assumps, &mut self.model, self.row_budget) && !cdcl.budget_hit {
                        bad_ub = Some(ub);
                        break;
                    }
                    for (i, &y) in self.exs.iter().enumerate() {
                        let key = extract(ub, self.dep_mask[i]) as usize;
                        if self.tables[i][key] == 0 {
                            self.tables[i][key] = if self.model[y as usize] > 0 { 1 } else { -1 };
                        }
                    }
                }
            }
            match bad_ub {
                None => {
                    for (j, &i) in self.outer.iter().enumerate() {
                        self.tables[i][0] = self.outer_pins[j].1;
                    }
                    let mut sk = build_skolem(&self.exs, &self.dep_lists, &self.tables);
                    crate::bce::reconstruct(&mut sk, f, &self.bce_stack);
                    self.mode = Mode::Exhausted;
                    return Step::Sat(Some(sk));
                }
                Some(ub) => {
                    self.bad_rows.push(ub);
                    // Deletion-core: try removing each outer pin; if still UNSAT,
                    // it wasn't needed.
                    let base = self.row_assumps(ub, &[]);
                    let mut core: Vec<(usize, i8)> = self
                        .outer_pins
                        .iter()
                        .enumerate()
                        .map(|(j, &(_, v))| (j, v))
                        .collect();
                    let mut k = 0;
                    while k < core.len() {
                        let mut a = base.clone();
                        for (jj, &(j, v)) in core.iter().enumerate() {
                            if jj == k {
                                continue;
                            }
                            let y = self.exs[self.outer[j]];
                            a.push(if v > 0 { y as Lit } else { -(y as Lit) });
                        }
                        if !cdcl.solve(&a, &mut self.model, self.row_budget) && !cdcl.budget_hit {
                            core.remove(k);
                        } else {
                            k += 1;
                        }
                    }
                    let block: Vec<Lit> = core
                        .iter()
                        .map(|&(j, v)| {
                            if v > 0 {
                                -((j + 1) as Lit)
                            } else {
                                (j + 1) as Lit
                            }
                        })
                        .collect();
                    self.outer_learned.push(block);
                    dbg_ex!(
                        debug,
                        "outer-CEGAR r{}: row {} UNSAT, core {}/{}, learned {}",
                        self.outer_learned.len(),
                        ub,
                        core.len(),
                        no,
                        self.outer_learned.len()
                    );
                }
            }
        }
    }
}
