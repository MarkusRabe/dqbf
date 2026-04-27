//! DQDIMACS parser. Port of `core/dqdimacs.py`; fuzz against it.

use std::collections::BTreeMap;

pub type Lit = i32;
pub type Clause = Vec<Lit>;

#[derive(Debug, Default, Clone)]
pub struct Formula {
    pub n_vars: u32,
    pub universals: Vec<u32>,
    pub dependencies: BTreeMap<u32, Vec<u32>>,
    pub clauses: Vec<Clause>,
}

#[derive(Debug)]
pub enum ParseError {
    BadHeader(String),
    BadLine(usize, String),
}

pub fn parse(text: &str) -> Result<Formula, ParseError> {
    let mut f = Formula::default();
    let mut seen_header = false;
    for (lineno, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('c') {
            continue;
        }
        let toks: Vec<&str> = line.split_whitespace().collect();
        match toks[0] {
            "p" => {
                if toks.len() != 4 || toks[1] != "cnf" {
                    return Err(ParseError::BadHeader(line.into()));
                }
                f.n_vars = toks[2].parse().map_err(|_| ParseError::BadHeader(line.into()))?;
                seen_header = true;
            }
            "a" | "e" | "d" => {
                if !seen_header {
                    return Err(ParseError::BadLine(lineno + 1, "before header".into()));
                }
                let nums: Vec<i32> =
                    toks[1..].iter().map(|t| t.parse().unwrap_or(0)).collect();
                let body: Vec<u32> = nums[..nums.len() - 1].iter().map(|&x| x as u32).collect();
                match toks[0] {
                    "a" => f.universals.extend(body),
                    "e" => {
                        let cur = f.universals.clone();
                        for y in body {
                            f.dependencies.insert(y, cur.clone());
                        }
                    }
                    "d" => {
                        let (y, ds) = body.split_first().ok_or_else(|| {
                            ParseError::BadLine(lineno + 1, "empty d".into())
                        })?;
                        f.dependencies.insert(*y, ds.to_vec());
                    }
                    _ => unreachable!(),
                }
            }
            _ => {
                let nums: Vec<i32> = toks.iter().map(|t| t.parse().unwrap_or(0)).collect();
                f.clauses.push(nums[..nums.len() - 1].to_vec());
            }
        }
    }
    Ok(f)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tiny() {
        let f = parse("p cnf 4 1\na 1 2 0\nd 3 1 0\nd 4 2 0\n3 4 0\n").unwrap();
        assert_eq!(f.n_vars, 4);
        assert_eq!(f.universals, vec![1, 2]);
        assert_eq!(f.dependencies.get(&3), Some(&vec![1]));
        assert_eq!(f.clauses, vec![vec![3, 4]]);
    }
}
