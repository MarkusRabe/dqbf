//! Port of `provers/forkres/{rules,search}.py`. Stub: returns Unknown.

use dqdimacs::Formula;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    Sat,
    Unsat,
    Unknown,
}

pub fn solve(_f: &Formula) -> Verdict {
    Verdict::Unknown
}
