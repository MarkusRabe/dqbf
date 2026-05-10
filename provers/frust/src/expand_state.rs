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
    /// One CDCL-refuted row of 2^|U|; carries the universal-polarity
    /// assumptions plus derived clauses (forcings ∪ partner cell-link
    /// constraints, each Q-resolution-derivable from `f.clauses`) so
    /// the caller can re-prove a `.frp` with forcing-chain stitching.
    UnsatRow(Vec<Lit>, Vec<Vec<Lit>>),
    /// Exhausted slot/arbiter space; no Skolem exists; no row-level cert.
    Unsat,
    Pending,
    Done,
}

enum Mode {
    Definability,
    Partial,
    OuterCegar,
    SlotDpll,
    Exhausted,
}

pub struct ExpandState {
    /// See `Config::trust_cell_link`.
    pub trust_cell_link: bool,
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
    outer_picker: Option<Cdcl>,
    outer_pins: Vec<(Var, i8)>,
    bad_rows: Vec<u32>,
    cegis_rows: usize,

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
        let n_inner = exs.len() - outer.len();
        let mode = if partial || multi_key {
            Mode::Definability
        } else if eae && !outer.is_empty() && (nu > 16 || (outer.len() > 12 && n_inner > 0)) {
            // OuterCegar searches outer-∃ via blocking-clause CDCL,
            // which scales where SlotDpll's 2^|outer| slot search
            // doesn't (circuit_synth has ~55 outer-∃ at |U|=2). At
            // n_inner=0 the problem is pure SAT and SlotDpll's single
            // free-pass solve is correct.
            Mode::OuterCegar
        } else {
            Mode::SlotDpll
        };
        let n = f.n_vars as usize + 1;
        let outer_pins: Vec<(Var, i8)> = outer.iter().map(|&i| (exs[i], -1i8)).collect();
        Self {
            trust_cell_link: true,
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
            outer_picker: None,
            outer_pins,
            bad_rows: Vec::new(),
            cegis_rows: 0,
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
                    // Coarse pre-gate on |E| only: interpolation runs
                    // O(|E|) Padoa solves, so genuinely huge instances
                    // (collatz n64) shouldn't pay the cost. The fine
                    // est_cells gate runs *after* interpolation — undef
                    // y's that become interpolated drop out of the cell
                    // count, so gating on `s.undefined` is too pessimistic.
                    if s.defined.len() + s.undefined.len() > 3000 {
                        self.mode = if nu_full > self.expand_us.len() {
                            Mode::Partial
                        } else {
                            Mode::SlotDpll
                        };
                        return self.step(f, cdcl, deadline, start, debug);
                    }
                    let itp_dl = start.elapsed().as_secs_f64() + (deadline - now) * 0.3;
                    let (defs, roots) = crate::definability::extract_interpolants(
                        f,
                        &s.defined,
                        &s.undefined,
                        itp_dl,
                        start,
                        debug,
                    );
                    let partner = crate::arbiter::detect_partners(f, &roots);
                    let n_pairs = partner.len() / 2;
                    let est_cells: usize = roots
                        .iter()
                        .filter(|&&y| partner.get(&y).map_or(true, |(p, _)| *p > y))
                        .map(|y| 1usize << f.deps[y].len().min(8))
                        .sum();
                    let eff_undef = roots.len().saturating_sub(n_pairs);
                    dbg_ex!(
                        debug,
                        "interpolated {}/{} (undef {}→{} roots, {} pairs, est_cells {})",
                        defs.len(),
                        s.defined.len() + s.undefined.len(),
                        s.undefined.len(),
                        roots.len(),
                        n_pairs,
                        est_cells,
                    );
                    if est_cells > 8192 && eff_undef > 100 {
                        self.mode = if nu_full > self.expand_us.len() {
                            Mode::Partial
                        } else {
                            Mode::SlotDpll
                        };
                        return self.step(f, cdcl, deadline, start, debug);
                    }
                    self.cegar = Some(crate::arbiter::CegarState::new(f, &roots, &defs, partner));
                    self.cegar.as_mut().unwrap().trust_cell_link = self.trust_cell_link;
                    self.cegar.as_mut().unwrap().defs = defs;
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
                // CEGAR runs on f.clauses (original, not post-BCE), so
                // the Skolem already satisfies the original matrix —
                // bce::reconstruct is unnecessary (and can't handle Aig).
                let sk = crate::arbiter::forcing_to_skolem(f, cert, 20).unwrap();
                Step::Sat(Some(sk))
            }
            CegarOut::UnsatRow(row, forcings) => {
                self.mode = Mode::Exhausted;
                Step::UnsatRow(row, forcings)
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
        if let Some(row) = deepening_partial_scan(f, cdcl, &mut self.model, deadline, start, debug)
        {
            self.mode = Mode::Exhausted;
            return Step::UnsatRow(row, Vec::new());
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
                    return Step::UnsatRow(assumps, Vec::new());
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
        let n = f.n_vars as usize;
        // Picker var space: 1..no are outer-∃; per accumulated
        // counterexample row, a fresh copy of all non-outer vars
        // (universals become picker-level units; inner-∃ + Tseitin aux
        // are free). Finding a model = a topology that simultaneously
        // satisfies the matrix on every accumulated row — CEGIS.
        // Cap row budget so the picker stays small enough for
        // pick_branch's linear scan; huge n_per_row falls back to
        // blocking-only.
        let n_per_row = n - no;
        // iter30's heap removes the linear-scan reason for the 32-row
        // cap. Budget the picker by total vars instead: enough rows to
        // cover 2^|U| when n_per_row is small (circuit_synth: 33×256 ≈
        // 8 k); fall back to blocking when rows would blow up.
        let cegis_rows: usize = (self.rows as usize).min(50_000 / n_per_row.max(1));
        let full = cegis_rows == self.rows as usize;
        let np = no + cegis_rows * n_per_row;
        let mut pmodel = vec![0i8; np + 1];
        let outer_set: HashSet<Var> = self.outer.iter().map(|&i| self.exs[i]).collect();
        let outer_idx: HashMap<Var, usize> = self
            .outer
            .iter()
            .enumerate()
            .map(|(j, &i)| (self.exs[i], j + 1))
            .collect();
        let nonouter: Vec<Var> = (1..=f.n_vars).filter(|v| !outer_set.contains(v)).collect();
        let nonouter_idx: HashMap<Var, usize> =
            nonouter.iter().enumerate().map(|(j, &v)| (v, j)).collect();
        if self.outer_picker.is_none() {
            let mut p = Cdcl::new(np, &self.outer_learned);
            for i in (no + 1)..=np {
                p.set_decision(i as u32, false);
            }
            // Full coverage fits the var budget — load every row upfront
            // instead of CEGIS one-by-one. A single picker solve then
            // decides: SAT ⇒ the model is a valid topology for all rows;
            // UNSAT ⇒ DQBF UNSAT.
            if full {
                let univ_set: HashSet<Var> = self.expand_us.iter().copied().collect();
                for ub in 0..self.rows {
                    let slot = ub as usize;
                    let base = no + slot * n_per_row;
                    // iter87: substitute the row's universal assignment
                    // in place of unit clauses + universal vars. The
                    // CEGIS-incremental path (line ~755) already does
                    // this; the full-expand path was added later
                    // (iter30) and missed it. For `csg_and8_k006`
                    // (256 rows × 870 clauses): drops ~50% of clauses
                    // (the satisfied ones) and removes universal vars
                    // from the picker's working set entirely. Same
                    // soundness — universal substitution is exactly
                    // what unit propagation would do.
                    let ubit: HashMap<Var, bool> = self
                        .expand_us
                        .iter()
                        .enumerate()
                        .map(|(i, &u)| (u, (ub >> i) & 1 == 1))
                        .collect();
                    for c in &f.clauses {
                        let mut sat = false;
                        let mut rc: Vec<Lit> = Vec::with_capacity(c.len());
                        for &l in c {
                            let v = crate::formula::var(l);
                            if let Some(&b) = ubit.get(&v) {
                                if (l > 0) == b {
                                    sat = true;
                                    break;
                                }
                                continue; // falsified universal lit
                            }
                            let pv = if let Some(&j) = outer_idx.get(&v) {
                                j as Lit
                            } else {
                                (base + 1 + nonouter_idx[&v]) as Lit
                            };
                            rc.push(if l > 0 { pv } else { -pv });
                        }
                        if !sat {
                            p.add_external(&rc);
                        }
                    }
                    for &v in &nonouter {
                        if !univ_set.contains(&v) {
                            p.set_decision((base + 1 + nonouter_idx[&v]) as u32, true);
                        }
                    }
                }
                self.cegis_rows = cegis_rows;
                dbg_ex!(
                    debug,
                    "outer-CEGAR full-expand: {} rows × {} vars",
                    self.rows,
                    n_per_row
                );
            }
            self.outer_picker = Some(p);
        }
        loop {
            if start.elapsed().as_secs_f64() > deadline {
                return Step::Pending;
            }
            let picker = self.outer_picker.as_mut().unwrap();
            for (j, &(_, v)) in self.outer_pins.iter().enumerate() {
                picker.set_phase((j + 1) as u32, v);
            }
            // Picker SAT can be hard once CEGIS row-matrices accumulate
            // (it's the synthesis problem). Chunk the budget so we yield
            // at the slice deadline rather than burning it on one solve.
            loop {
                if !picker.solve(&[], &mut pmodel, 10_000) {
                    if picker.budget_hit {
                        if start.elapsed().as_secs_f64() > deadline {
                            return Step::Pending;
                        }
                        continue;
                    }
                    dbg_ex!(
                        debug,
                        "outer-CEGAR picker UNSAT after {} rows, {} blocks",
                        self.cegis_rows,
                        self.outer_learned.len()
                    );
                    self.mode = Mode::Exhausted;
                    return Step::Unsat;
                }
                break;
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
            // Random fuzz before the linear scan: when |U| is large the
            // bad rows are sparse and the linear-from-0 scan wastes time
            // re-solving already-good rows. xorshift hits the row space
            // uniformly; the linear scan still guarantees coverage.
            if bad_ub.is_none() && self.rows > 1024 {
                let mut s = 0x9e3779b9u32 ^ (self.bad_rows.len() as u32).wrapping_mul(2654435761);
                for _ in 0..256 {
                    s ^= s << 13;
                    s ^= s >> 17;
                    s ^= s << 5;
                    let ub = s % self.rows;
                    let assumps = self.row_assumps(ub, &self.outer_pins);
                    if !cdcl.solve(&assumps, &mut self.model, self.row_budget) && !cdcl.budget_hit {
                        bad_ub = Some(ub);
                        break;
                    }
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
                    // CEGIS: add a matrix copy at row ub to the picker
                    // so the next candidate must satisfy this row too.
                    // Shared: outer-∃ → picker[1..no]. Fresh: everything
                    // else (universals pinned by units; inner free).
                    let slot = self.cegis_rows;
                    if slot < cegis_rows && !self.bad_rows[..self.bad_rows.len() - 1].contains(&ub)
                    {
                        self.cegis_rows += 1;
                        let base = no + slot * n_per_row;
                        let remap = |l: Lit| -> Lit {
                            let v = crate::formula::var(l);
                            let pv = if let Some(&j) = outer_idx.get(&v) {
                                j as Lit
                            } else {
                                (base + 1 + nonouter_idx[&v]) as Lit
                            };
                            if l > 0 {
                                pv
                            } else {
                                -pv
                            }
                        };
                        // The universal assignment for this row is fixed
                        // (`ub`). Substitute it into the matrix copy
                        // before adding: clauses satisfied by a universal
                        // lit are skipped entirely; falsified universal
                        // lits are dropped. For a typical circuit-synth
                        // matrix this halves the clause count per row and
                        // removes the universal vars from the picker's
                        // propagation working set — the CDCL never has to
                        // propagate them off the unit clauses each round.
                        let ubit: HashMap<Var, bool> = self
                            .expand_us
                            .iter()
                            .enumerate()
                            .map(|(i, &u)| (u, (ub >> i) & 1 == 1))
                            .collect();
                        let picker = self.outer_picker.as_mut().unwrap();
                        let mut n_added = 0usize;
                        let mut touched: HashSet<Var> = HashSet::new();
                        for c in &f.clauses {
                            let mut sat = false;
                            let mut rc: Vec<Lit> = Vec::with_capacity(c.len());
                            for &l in c {
                                let v = crate::formula::var(l);
                                if let Some(&b) = ubit.get(&v) {
                                    if (l > 0) == b {
                                        sat = true;
                                        break;
                                    }
                                    continue; // falsified universal lit
                                }
                                rc.push(remap(l));
                                touched.insert(v);
                            }
                            if sat || rc.is_empty() {
                                continue;
                            }
                            picker.add_external(&rc);
                            n_added += 1;
                        }
                        // Only enable decision on the inner-∃ vars that
                        // actually survive the substitution (the cone of
                        // this row's residual matrix).
                        for &v in &nonouter {
                            if !ubit.contains_key(&v) && touched.contains(&v) {
                                picker.set_decision((base + 1 + nonouter_idx[&v]) as u32, true);
                            }
                        }
                        let _ = n_added;
                        dbg_ex!(
                            debug,
                            "outer-CEGAR r{}: cegis row {} (slot {})",
                            self.bad_rows.len(),
                            ub,
                            slot
                        );
                        continue;
                    }
                    // Seed deletion-min from analyze_final's core (the
                    // outer-∃ subset of the failed assumption set)
                    // instead of from all |outer| pins — at 357 outer-∃
                    // the full sweep is 357 solves/round.
                    let base = self.row_assumps(ub, &[]);
                    let mut a = base.clone();
                    for &(y, v) in &self.outer_pins {
                        a.push(if v > 0 { y as Lit } else { -(y as Lit) });
                    }
                    cdcl.solve(&a, &mut self.model, self.row_budget);
                    let last_core: HashSet<Var> = cdcl
                        .last_core()
                        .iter()
                        .map(|&l| crate::formula::var(l))
                        .collect();
                    let mut core: Vec<(usize, i8)> = self
                        .outer_pins
                        .iter()
                        .enumerate()
                        .filter(|(_, &(y, _))| last_core.contains(&y))
                        .map(|(j, &(_, v))| (j, v))
                        .collect();
                    if core.is_empty() {
                        core = self
                            .outer_pins
                            .iter()
                            .enumerate()
                            .map(|(j, &(_, v))| (j, v))
                            .collect();
                    }
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
                    self.outer_picker.as_mut().unwrap().add_external(&block);
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
