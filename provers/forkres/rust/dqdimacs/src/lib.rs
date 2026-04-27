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

fn parse_nums<T: std::str::FromStr>(toks: &[&str], lineno: usize) -> Result<Vec<T>, ParseError> {
    toks.iter()
        .map(|t| {
            t.parse()
                .map_err(|_| ParseError::BadLine(lineno, format!("bad token {t:?}")))
        })
        .collect()
}

fn body_u32(toks: &[&str], lineno: usize) -> Result<Vec<u32>, ParseError> {
    let nums: Vec<i32> = parse_nums(toks, lineno)?;
    if nums.last() != Some(&0) {
        return Err(ParseError::BadLine(lineno, "not 0-terminated".into()));
    }
    Ok(nums[..nums.len() - 1].iter().map(|&x| x as u32).collect())
}

pub fn parse(text: &str) -> Result<Formula, ParseError> {
    let mut f = Formula::default();
    let mut seen_header = false;
    for (i, raw) in text.lines().enumerate() {
        let lineno = i + 1;
        let line = raw.trim();
        if line.is_empty() || line.starts_with('c') {
            continue;
        }
        let toks: Vec<&str> = line.split_whitespace().collect();
        match toks[0] {
            "p" => {
                if seen_header {
                    return Err(ParseError::BadHeader("duplicate header".into()));
                }
                if toks.len() != 4 || toks[1] != "cnf" {
                    return Err(ParseError::BadHeader(line.into()));
                }
                f.n_vars = toks[2]
                    .parse()
                    .map_err(|_| ParseError::BadHeader(line.into()))?;
                seen_header = true;
            }
            "a" | "e" | "d" => {
                if !seen_header {
                    return Err(ParseError::BadLine(lineno, "before header".into()));
                }
                let body = body_u32(&toks[1..], lineno)?;
                match toks[0] {
                    "a" => f.universals.extend(body),
                    "e" => {
                        let cur = f.universals.clone();
                        for y in body {
                            f.dependencies.insert(y, cur.clone());
                        }
                    }
                    "d" => {
                        let (y, ds) = body
                            .split_first()
                            .ok_or_else(|| ParseError::BadLine(lineno, "empty d".into()))?;
                        f.dependencies.insert(*y, ds.to_vec());
                    }
                    _ => unreachable!(),
                }
            }
            _ => {
                if !seen_header {
                    return Err(ParseError::BadLine(lineno, "before header".into()));
                }
                let nums: Vec<i32> = parse_nums(&toks, lineno)?;
                if nums.last() != Some(&0) {
                    return Err(ParseError::BadLine(lineno, "not 0-terminated".into()));
                }
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

    #[test]
    fn rejects_bad_token() {
        assert!(parse("p cnf 2 1\na 1 abc 0\n").is_err());
        assert!(parse("p cnf 2 1\na 1 0\n1a 2 0\n").is_err());
    }

    #[test]
    fn rejects_missing_terminator() {
        assert!(parse("p cnf 2 0\na 1 2\n").is_err());
        assert!(parse("p cnf 2 0\na\n").is_err());
        assert!(parse("p cnf 2 1\na 1 0\n1 2\n").is_err());
    }

    #[test]
    fn rejects_data_before_header() {
        assert!(parse("3 4 0\np cnf 4 0\n").is_err());
    }

    #[test]
    fn rejects_duplicate_header() {
        assert!(parse("p cnf 2 1\np cnf 5 1\n").is_err());
    }
}
