//! ASCII AIGER (.aag) reader, derived from the AIGER spec
//! (https://fmv.jku.at/aiger/FORMAT). Independent of `provers/` and
//! `tools/verify/`.
//!
//! AIGER literals: even = positive, odd = negation; 0 = false, 1 = true.
//! Variable index of literal `l` is `l >> 1`.

use std::collections::BTreeMap;

#[derive(Debug)]
pub struct Aag {
    pub max_var: u64,
    pub inputs: Vec<u64>,            // even literals
    pub outputs: Vec<u64>,           // arbitrary literals
    pub gates: Vec<(u64, u64, u64)>, // (lhs even literal, rhs0, rhs1)
    /// Symbol table: kind (b'i'/b'o'/b'l') × index → name.
    pub symbols: BTreeMap<(u8, usize), String>,
}

#[derive(Debug)]
pub struct ParseErr(pub String);
impl std::fmt::Display for ParseErr {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "aiger parse error: {}", self.0)
    }
}

pub fn parse(text: &str) -> Result<Aag, ParseErr> {
    let mut lines = text.lines().map(str::trim).filter(|l| !l.is_empty());
    let header = lines.next().ok_or_else(|| ParseErr("empty file".into()))?;
    let h: Vec<&str> = header.split_whitespace().collect();
    if h.len() != 6 || h[0] != "aag" {
        return Err(ParseErr(format!("bad header: {header}")));
    }
    let pn = |s: &str, what: &str| -> Result<u64, ParseErr> {
        s.parse::<u64>()
            .map_err(|_| ParseErr(format!("bad {what} in header: {s}")))
    };
    let m = pn(h[1], "M")?;
    let i = pn(h[2], "I")?;
    let l = pn(h[3], "L")?;
    let o = pn(h[4], "O")?;
    let a = pn(h[5], "A")?;
    if l != 0 {
        return Err(ParseErr(format!("latches unsupported (L={l})")));
    }
    if i + l + a != m {
        return Err(ParseErr(format!(
            "header inconsistent: M={m} but I+L+A={}",
            i + l + a
        )));
    }
    let max_lit = 2 * m + 1;
    let pl = |s: &str, what: &str| -> Result<u64, ParseErr> {
        let v = pn(s, what)?;
        if v > max_lit {
            return Err(ParseErr(format!("{what} literal {v} > 2*M+1={max_lit}")));
        }
        Ok(v)
    };

    let mut inputs = Vec::with_capacity(i as usize);
    for k in 0..i {
        let s = lines
            .next()
            .ok_or_else(|| ParseErr(format!("missing input {k}")))?;
        let lit = pl(s, "input")?;
        if lit % 2 != 0 || lit == 0 {
            return Err(ParseErr(format!("input must be a positive even literal: {lit}")));
        }
        inputs.push(lit);
    }
    let mut outputs = Vec::with_capacity(o as usize);
    for k in 0..o {
        let s = lines
            .next()
            .ok_or_else(|| ParseErr(format!("missing output {k}")))?;
        outputs.push(pl(s, "output")?);
    }
    let mut gates = Vec::with_capacity(a as usize);
    let mut defined: std::collections::BTreeSet<u64> =
        inputs.iter().map(|&x| x >> 1).collect();
    for k in 0..a {
        let s = lines
            .next()
            .ok_or_else(|| ParseErr(format!("missing gate {k}")))?;
        let toks: Vec<&str> = s.split_whitespace().collect();
        if toks.len() != 3 {
            return Err(ParseErr(format!("gate {k}: expected 3 tokens")));
        }
        let lhs = pl(toks[0], "gate lhs")?;
        let r0 = pl(toks[1], "gate rhs0")?;
        let r1 = pl(toks[2], "gate rhs1")?;
        if lhs % 2 != 0 || lhs == 0 {
            return Err(ParseErr(format!("gate lhs must be positive even: {lhs}")));
        }
        if defined.contains(&(lhs >> 1)) {
            return Err(ParseErr(format!("gate redefines var {}", lhs >> 1)));
        }
        defined.insert(lhs >> 1);
        gates.push((lhs, r0, r1));
    }
    // Symbol table + comment.
    let mut symbols = BTreeMap::new();
    for line in lines {
        if line.starts_with('c') && !line.contains(' ') {
            break;
        }
        if let Some(rest) = line.strip_prefix('i') {
            let (idx, name) = split_sym(rest)?;
            symbols.insert((b'i', idx), name);
        } else if let Some(rest) = line.strip_prefix('o') {
            let (idx, name) = split_sym(rest)?;
            symbols.insert((b'o', idx), name);
        } else if let Some(rest) = line.strip_prefix('l') {
            let (idx, name) = split_sym(rest)?;
            symbols.insert((b'l', idx), name);
        } else if line.starts_with('c') {
            break;
        } else {
            return Err(ParseErr(format!("unexpected line: {line}")));
        }
    }
    Ok(Aag {
        max_var: m,
        inputs,
        outputs,
        gates,
        symbols,
    })
}

fn split_sym(rest: &str) -> Result<(usize, String), ParseErr> {
    let mut parts = rest.splitn(2, ' ');
    let idx = parts
        .next()
        .ok_or_else(|| ParseErr("malformed symbol".into()))?
        .parse::<usize>()
        .map_err(|_| ParseErr("malformed symbol index".into()))?;
    let name = parts
        .next()
        .ok_or_else(|| ParseErr("symbol with no name".into()))?
        .to_string();
    Ok((idx, name))
}

pub fn load(path: &std::path::Path) -> Result<Aag, ParseErr> {
    let text = std::fs::read_to_string(path).map_err(|e| ParseErr(format!("read {path:?}: {e}")))?;
    parse(&text)
}
