//! Minimal .aag writer for Skolem certificates.

use crate::formula::{var, Formula, Lit, Var};
use std::collections::{BTreeMap, HashMap};
use std::io::Write;

/// One Skolem function. `Table` is a 2^ndeps-bit truth table; `Clauses`
/// is a priority list of `(ante, polarity)` cubes over dep(y) (first
/// match wins, default 0). `Aig` is a McMillan interpolant — inputs may
/// be universals *or other existentials* (with smaller dep), so the
/// writer must emit those first and reference their output gates.
pub enum SkolemFn {
    Table(Vec<u64>, usize),
    Clauses(Vec<(Vec<Lit>, bool)>),
    Aig(crate::interpolant::Itp, u32),
}

pub type Skolem = BTreeMap<Var, SkolemFn>;

struct Aig {
    n_inputs: usize,
    gates: Vec<(u32, u32, u32)>,
    strash: HashMap<(u32, u32), u32>,
}

impl Aig {
    fn lit_input(&self, i: usize) -> u32 {
        2 * (i as u32 + 1)
    }
    fn max_var(&self) -> u32 {
        self.n_inputs as u32 + self.gates.len() as u32
    }
    fn mk_and(&mut self, a: u32, b: u32) -> u32 {
        if a == 0 || b == 0 {
            return 0;
        }
        if a == 1 {
            return b;
        }
        if b == 1 {
            return a;
        }
        if a == b {
            return a;
        }
        if a == (b ^ 1) {
            return 0;
        }
        let key = if a < b { (a, b) } else { (b, a) };
        if let Some(&g) = self.strash.get(&key) {
            return g;
        }
        let v = self.max_var() + 1;
        self.gates.push((2 * v, a, b));
        self.strash.insert(key, 2 * v);
        2 * v
    }
    fn mk_or(&mut self, a: u32, b: u32) -> u32 {
        self.mk_and(a ^ 1, b ^ 1) ^ 1
    }
    fn mk_ite(&mut self, c: u32, t: u32, e: u32) -> u32 {
        let a = self.mk_and(c, t);
        let b = self.mk_and(c ^ 1, e);
        self.mk_or(a, b)
    }
}

fn shannon(aig: &mut Aig, bits: &[u64], n: usize, inputs: &[u32]) -> u32 {
    let mut memo: HashMap<(usize, Vec<u64>), u32> = HashMap::new();
    rec(aig, bits, 0, n, inputs, &mut memo)
}

fn rec(
    aig: &mut Aig,
    bits: &[u64],
    depth: usize,
    n: usize,
    ins: &[u32],
    memo: &mut HashMap<(usize, Vec<u64>), u32>,
) -> u32 {
    let span = 1usize << (n - depth);
    if span == 1 {
        return (bits[0] & 1) as u32;
    }
    // Check constant.
    let words = span.div_ceil(64);
    let all_zero = bits[..words].iter().all(|&w| w == 0);
    if all_zero {
        return 0;
    }
    let mask_last = if span.is_multiple_of(64) {
        u64::MAX
    } else {
        (1u64 << (span % 64)) - 1
    };
    let all_one = bits[..words.saturating_sub(1)]
        .iter()
        .all(|&w| w == u64::MAX)
        && (words == 0 || bits[words - 1] & mask_last == mask_last);
    if all_one {
        return 1;
    }
    let key = (depth, bits[..words].to_vec());
    if let Some(&g) = memo.get(&key) {
        return g;
    }
    // Cofactor on input[depth]: low half (bit=0) and high half (bit=1).
    let half = span / 2;
    let hw = half.div_ceil(64);
    let mut lo = vec![0u64; hw];
    let mut hi = vec![0u64; hw];
    for i in 0..half {
        if bits[i / 64] >> (i % 64) & 1 == 1 {
            lo[i / 64] |= 1 << (i % 64);
        }
        let j = i + half;
        if bits[j / 64] >> (j % 64) & 1 == 1 {
            hi[i / 64] |= 1 << (i % 64);
        }
    }
    let e = rec(aig, &lo, depth + 1, n, ins, memo);
    let t = rec(aig, &hi, depth + 1, n, ins, memo);
    // Halving the bitmap splits on the highest remaining index bit.
    let sel = ins[n - 1 - depth];
    let out = if t == e {
        t
    } else if t == 1 && e == 0 {
        sel
    } else if t == 0 && e == 1 {
        sel ^ 1
    } else {
        aig.mk_ite(sel, t, e)
    };
    memo.insert(key, out);
    out
}

pub fn write_skolem_aag<W: Write>(w: &mut W, f: &Formula, sk: &Skolem) -> std::io::Result<()> {
    let mut aig = Aig {
        n_inputs: f.universals.len(),
        gates: Vec::new(),
        strash: HashMap::new(),
    };
    let u_lit: BTreeMap<Var, u32> = f
        .universals
        .iter()
        .enumerate()
        .map(|(i, &u)| (u, aig.lit_input(i)))
        .collect();
    let mut outputs: Vec<(Var, u32)> = Vec::new();
    let mut out_lit: HashMap<Var, u32> = HashMap::new();
    // `Aig` inputs may reference other existentials z (via linked-z
    // interpolation). DFS post-order over the y→z reference graph.
    let order: Vec<Var> = {
        let refs: HashMap<Var, Vec<Var>> = sk
            .iter()
            .map(|(&y, fn_)| {
                let r = if let SkolemFn::Aig(itp, _) = fn_ {
                    itp.inputs
                        .iter()
                        .copied()
                        .filter(|v| sk.contains_key(v))
                        .collect()
                } else {
                    Vec::new()
                };
                (y, r)
            })
            .collect();
        let mut order = Vec::with_capacity(sk.len());
        let mut state: HashMap<Var, u8> = HashMap::new();
        let mut stack: Vec<(Var, usize)> = Vec::new();
        for &y0 in sk.keys() {
            if state.contains_key(&y0) {
                continue;
            }
            stack.push((y0, 0));
            while let Some(&mut (y, ref mut i)) = stack.last_mut() {
                state.insert(y, 1);
                let r = &refs[&y];
                if *i < r.len() {
                    let z = r[*i];
                    *i += 1;
                    if !state.contains_key(&z) {
                        stack.push((z, 0));
                    }
                } else {
                    order.push(y);
                    state.insert(y, 2);
                    stack.pop();
                }
            }
        }
        order
    };
    for &y in &order {
        let fn_ = &sk[&y];
        let out = match fn_ {
            SkolemFn::Table(bits, ndeps) => {
                let deps: Vec<Var> = f
                    .deps
                    .get(&y)
                    .map(|d| d.iter().copied().collect())
                    .unwrap_or_default();
                let ins: Vec<u32> = deps.iter().take(*ndeps).map(|d| u_lit[d]).collect();
                shannon(&mut aig, bits, ins.len(), &ins)
            }
            SkolemFn::Aig(itp, root) => {
                use crate::interpolant::NodeKind;
                let map_in = |v: Var| -> u32 {
                    u_lit
                        .get(&v)
                        .or_else(|| out_lit.get(&v))
                        .copied()
                        .unwrap_or_else(|| {
                            panic!("interpolant for {y} references {v} not yet emitted")
                        })
                };
                let mut gate_lit = vec![0u32; itp.gates.len()];
                let to_aig = |l: u32, gate_lit: &[u32]| -> u32 {
                    let base = match itp.node_kind(l) {
                        NodeKind::Const => return l,
                        NodeKind::Input(i) => map_in(itp.inputs[i]),
                        NodeKind::Gate(k) => gate_lit[k],
                    };
                    base ^ (l & 1)
                };
                for (k, &(a, b)) in itp.gates.iter().enumerate() {
                    gate_lit[k] = aig.mk_and(to_aig(a, &gate_lit), to_aig(b, &gate_lit));
                }
                to_aig(*root, &gate_lit)
            }
            SkolemFn::Clauses(cubes) => {
                // Priority decoder: scan cubes in order; first hit
                // wins. y = ⋁ [hitᵢ ∧ valᵢ ∧ ⋀_{j<i} ¬hitⱼ]. With
                // default 0 the negative cubes only contribute the
                // "stop here" guard.
                let mut acc = 0u32; // default false
                let mut not_yet = 1u32; // ⋀ ¬hitⱼ so far (true)
                for (ante, val) in cubes {
                    let mut hit = 1u32;
                    for &l in ante {
                        let ul = u_lit[&var(l)] ^ if l < 0 { 1 } else { 0 };
                        hit = aig.mk_and(hit, ul);
                    }
                    if *val {
                        let take = aig.mk_and(not_yet, hit);
                        acc = aig.mk_or(acc, take);
                    }
                    not_yet = aig.mk_and(not_yet, hit ^ 1);
                }
                acc
            }
        };
        out_lit.insert(y, out);
        outputs.push((y, out));
    }
    let m = aig.max_var();
    writeln!(
        w,
        "aag {} {} 0 {} {}",
        m,
        aig.n_inputs,
        outputs.len(),
        aig.gates.len()
    )?;
    for i in 0..aig.n_inputs {
        writeln!(w, "{}", aig.lit_input(i))?;
    }
    for &(_, o) in &outputs {
        writeln!(w, "{}", o)?;
    }
    for &(g, a, b) in &aig.gates {
        writeln!(w, "{} {} {}", g, a, b)?;
    }
    for (i, &u) in f.universals.iter().enumerate() {
        writeln!(w, "i{} u{}", i, u)?;
    }
    for (i, &(y, _)) in outputs.iter().enumerate() {
        writeln!(w, "o{} e{}", i, y)?;
    }
    Ok(())
}
