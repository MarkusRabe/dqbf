//! Minimal .aag writer for Skolem certificates.

use crate::formula::{Formula, Var};
use std::collections::BTreeMap;
use std::io::Write;

/// Per-existential: (truth-table bitmap of length 2^ndeps bits, ndeps).
pub type Skolem = BTreeMap<Var, (Vec<u64>, usize)>;

struct Aig {
    n_inputs: usize,
    gates: Vec<(u32, u32, u32)>,
}

impl Aig {
    fn lit_input(&self, i: usize) -> u32 {
        2 * (i as u32 + 1)
    }
    fn max_var(&self) -> u32 {
        self.n_inputs as u32 + self.gates.len() as u32
    }
    fn mk_and(&mut self, a: u32, b: u32) -> u32 {
        let v = self.max_var() + 1;
        self.gates.push((2 * v, a, b));
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

use std::collections::HashMap;

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
    let words = (span + 63) / 64;
    let all_zero = bits[..words].iter().all(|&w| w == 0);
    if all_zero {
        return 0;
    }
    let mask_last = if span % 64 == 0 {
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
    let hw = (half + 63) / 64;
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
    };
    let u_lit: BTreeMap<Var, u32> = f
        .universals
        .iter()
        .enumerate()
        .map(|(i, &u)| (u, aig.lit_input(i)))
        .collect();
    let mut outputs: Vec<(Var, u32)> = Vec::new();
    for (&y, (bits, ndeps)) in sk {
        let deps: Vec<Var> = f.deps[&y].iter().copied().collect();
        let ins: Vec<u32> = deps.iter().map(|d| u_lit[d]).collect();
        let out = shannon(&mut aig, bits, *ndeps, &ins);
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
