//! DQDIMACS parser (handles plain text; gzip handled by the caller).

use crate::formula::{Clause, Formula, Var};
use std::collections::{BTreeMap, BTreeSet};

pub fn parse(text: &str) -> Result<Formula, String> {
    let mut n_vars: u32 = 0;
    let mut seen_header = false;
    let mut universals: Vec<Var> = Vec::new();
    let mut deps: BTreeMap<Var, BTreeSet<Var>> = BTreeMap::new();
    let mut clauses: Vec<Clause> = Vec::new();

    for (lineno, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('c') {
            continue;
        }
        let mut toks = line.split_whitespace();
        let head = toks.clone().next().unwrap_or("");
        match head {
            "p" => {
                let v: Vec<&str> = line.split_whitespace().collect();
                if seen_header || v.len() != 4 || v[1] != "cnf" {
                    return Err(format!("line {}: bad header", lineno + 1));
                }
                n_vars = v[2].parse().map_err(|_| "bad n_vars")?;
                seen_header = true;
            }
            "a" | "e" | "d" => {
                if !seen_header {
                    return Err(format!("line {}: before header", lineno + 1));
                }
                toks.next();
                let nums: Result<Vec<i32>, _> = toks.map(|t| t.parse()).collect();
                let nums = nums.map_err(|_| format!("line {}: bad token", lineno + 1))?;
                if nums.last() != Some(&0) {
                    return Err(format!("line {}: not 0-terminated", lineno + 1));
                }
                let body: Vec<u32> = nums[..nums.len() - 1].iter().map(|&x| x as u32).collect();
                match head {
                    "a" => universals.extend(body),
                    "e" => {
                        let cur: BTreeSet<Var> = universals.iter().copied().collect();
                        for y in body {
                            deps.insert(y, cur.clone());
                        }
                    }
                    "d" => {
                        if body.is_empty() {
                            return Err(format!("line {}: empty d", lineno + 1));
                        }
                        let (y, ds) = body.split_first().unwrap();
                        deps.insert(*y, ds.iter().copied().collect());
                    }
                    _ => unreachable!(),
                }
            }
            _ => {
                if !seen_header {
                    return Err(format!("line {}: before header", lineno + 1));
                }
                let nums: Result<Vec<i32>, _> =
                    line.split_whitespace().map(|t| t.parse()).collect();
                let nums = nums.map_err(|_| format!("line {}: bad token", lineno + 1))?;
                if nums.last() != Some(&0) {
                    return Err(format!("line {}: not 0-terminated", lineno + 1));
                }
                let mut cl: Clause = nums[..nums.len() - 1].to_vec();
                cl.sort_unstable();
                cl.dedup();
                clauses.push(cl);
            }
        }
    }
    Ok(Formula::new(n_vars, universals, deps, clauses))
}
