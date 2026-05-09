//! DQDIMACS reader, derived from `docs/references/dqdimacs.md`.
//! Independent of `provers/` and `tools/verify/`.

use std::collections::{BTreeMap, BTreeSet};

pub type Var = i64;
pub type Lit = i64;
pub type Clause = BTreeSet<Lit>;

#[derive(Debug, Clone)]
pub struct Formula {
    pub n_vars: Var,
    /// Universals in declaration order.
    pub universals: Vec<Var>,
    /// Existential -> dependency set (universal vars).
    pub deps: BTreeMap<Var, BTreeSet<Var>>,
    pub clauses: Vec<Clause>,
}

impl Formula {
    pub fn is_universal(&self, v: Var) -> bool {
        self.universals.contains(&v)
    }
    pub fn is_existential(&self, v: Var) -> bool {
        self.deps.contains_key(&v)
    }
}

#[derive(Debug)]
pub struct ParseErr(pub String);

impl std::fmt::Display for ParseErr {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "dqdimacs parse error: {}", self.0)
    }
}

pub fn parse(text: &str) -> Result<Formula, ParseErr> {
    let mut n_vars: Var = 0;
    let mut header_seen = false;
    let mut universals: Vec<Var> = Vec::new();
    let mut universal_set: BTreeSet<Var> = BTreeSet::new();
    let mut deps: BTreeMap<Var, BTreeSet<Var>> = BTreeMap::new();
    let mut clauses: Vec<Clause> = Vec::new();

    for (no, raw) in text.lines().enumerate() {
        let lno = no + 1;
        let line = raw.trim();
        if line.is_empty() || line.starts_with('c') {
            continue;
        }
        let mut toks = line.split_whitespace().peekable();
        let head = *toks.peek().unwrap_or(&"");
        match head {
            "p" => {
                if header_seen {
                    return Err(ParseErr(format!("line {lno}: duplicate header")));
                }
                let parts: Vec<&str> = line.split_whitespace().collect();
                if parts.len() != 4 || parts[1] != "cnf" {
                    return Err(ParseErr(format!("line {lno}: bad header")));
                }
                n_vars = parts[2]
                    .parse()
                    .map_err(|_| ParseErr(format!("line {lno}: bad n_vars")))?;
                if n_vars < 0 {
                    return Err(ParseErr(format!("line {lno}: negative n_vars")));
                }
                header_seen = true;
            }
            "a" | "e" | "d" => {
                if !header_seen {
                    return Err(ParseErr(format!("line {lno}: prefix before header")));
                }
                toks.next(); // consume head
                let nums: Result<Vec<Lit>, _> = toks.map(|t| t.parse::<Lit>()).collect();
                let nums = nums.map_err(|_| ParseErr(format!("line {lno}: non-integer")))?;
                if nums.last() != Some(&0) {
                    return Err(ParseErr(format!("line {lno}: not 0-terminated")));
                }
                let body = &nums[..nums.len() - 1];
                if body.iter().any(|&v| v <= 0) {
                    return Err(ParseErr(format!(
                        "line {lno}: prefix entries must be positive"
                    )));
                }
                if body.iter().any(|&v| v > n_vars) {
                    return Err(ParseErr(format!("line {lno}: var > n_vars")));
                }
                match head {
                    "a" => {
                        for &v in body {
                            if universal_set.contains(&v) || deps.contains_key(&v) {
                                return Err(ParseErr(format!(
                                    "line {lno}: var {v} declared twice"
                                )));
                            }
                            universals.push(v);
                            universal_set.insert(v);
                        }
                    }
                    "e" => {
                        let cur: BTreeSet<Var> = universal_set.iter().copied().collect();
                        for &v in body {
                            if universal_set.contains(&v) || deps.contains_key(&v) {
                                return Err(ParseErr(format!(
                                    "line {lno}: var {v} declared twice"
                                )));
                            }
                            deps.insert(v, cur.clone());
                        }
                    }
                    "d" => {
                        if body.is_empty() {
                            return Err(ParseErr(format!("line {lno}: empty d-line")));
                        }
                        let y = body[0];
                        if universal_set.contains(&y) || deps.contains_key(&y) {
                            return Err(ParseErr(format!("line {lno}: var {y} declared twice")));
                        }
                        let ds: BTreeSet<Var> = body[1..].iter().copied().collect();
                        for &u in &ds {
                            if !universal_set.contains(&u) {
                                return Err(ParseErr(format!(
                                    "line {lno}: d-line dep {u} is not a declared universal"
                                )));
                            }
                        }
                        deps.insert(y, ds);
                    }
                    _ => unreachable!(),
                }
            }
            _ => {
                if !header_seen {
                    return Err(ParseErr(format!("line {lno}: clause before header")));
                }
                let nums: Result<Vec<Lit>, _> =
                    line.split_whitespace().map(|t| t.parse::<Lit>()).collect();
                let nums = nums.map_err(|_| ParseErr(format!("line {lno}: non-integer")))?;
                if nums.last() != Some(&0) {
                    return Err(ParseErr(format!("line {lno}: not 0-terminated")));
                }
                let mut c: Clause = BTreeSet::new();
                for &l in &nums[..nums.len() - 1] {
                    if l == 0 {
                        return Err(ParseErr(format!("line {lno}: 0 inside clause")));
                    }
                    if l.abs() > n_vars {
                        return Err(ParseErr(format!("line {lno}: var > n_vars")));
                    }
                    c.insert(l);
                }
                clauses.push(c);
            }
        }
    }
    if !header_seen {
        return Err(ParseErr("no header".into()));
    }
    Ok(Formula {
        n_vars,
        universals,
        deps,
        clauses,
    })
}

/// Read possibly-gzipped DQDIMACS from a file path.
pub fn load(path: &std::path::Path) -> Result<Formula, ParseErr> {
    let raw = std::fs::read(path).map_err(|e| ParseErr(format!("read {path:?}: {e}")))?;
    let text = if raw.len() >= 2 && raw[0] == 0x1f && raw[1] == 0x8b {
        use flate2::read::GzDecoder;
        use std::io::Read;
        let mut s = String::new();
        GzDecoder::new(&raw[..])
            .read_to_string(&mut s)
            .map_err(|e| ParseErr(format!("gunzip {path:?}: {e}")))?;
        s
    } else {
        String::from_utf8(raw).map_err(|e| ParseErr(format!("utf8 {path:?}: {e}")))?
    };
    parse(&text)
}
