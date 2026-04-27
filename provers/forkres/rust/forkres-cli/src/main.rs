use std::io::{self, Read};
use std::process::ExitCode;

use forkres_core::{solve, Verdict};

fn main() -> ExitCode {
    let mut text = String::new();
    let path = std::env::args().nth(1);
    match path {
        Some(p) => text = std::fs::read_to_string(p).expect("read input"),
        None => {
            io::stdin().read_to_string(&mut text).expect("read stdin");
        }
    }
    let f = dqdimacs::parse(&text).expect("parse");
    let v = solve(&f);
    let (name, code) = match v {
        Verdict::Sat => ("SAT", 10),
        Verdict::Unsat => ("UNSAT", 20),
        Verdict::Unknown => ("UNKNOWN", 0),
    };
    println!("{name}");
    ExitCode::from(code)
}
