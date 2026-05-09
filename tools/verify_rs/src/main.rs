//! `dqbf-verify-rs` — independent DQBF certificate checker.
//! Mirrors the *interface* of `tools/verify/cli.py` but shares no code.
//!
//! Usage:
//!   dqbf-verify-rs sat   FORMULA.dqdimacs[.gz] CERT.aag [--solver PATH]
//!   dqbf-verify-rs unsat FORMULA.dqdimacs[.gz] PROOF.frp
//!
//! Prints `VALID` or `INVALID` (or `DEP-VIOLATION`) and exits 0 on
//! VALID, 1 otherwise.

mod aiger;
mod dqdimacs;
mod frp;
mod sat;
mod unsat;

use std::path::PathBuf;
use std::process::exit;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() < 3 {
        eprintln!("usage: dqbf-verify-rs {{sat|unsat}} FORMULA CERT [--solver PATH]");
        exit(2);
    }
    let mode = &args[0];
    let formula_path = PathBuf::from(&args[1]);
    let cert_path = PathBuf::from(&args[2]);
    let solver = args
        .iter()
        .position(|a| a == "--solver")
        .and_then(|i| args.get(i + 1))
        .map(PathBuf::from)
        .unwrap_or_else(default_solver);

    let f = match dqdimacs::load(&formula_path) {
        Ok(f) => f,
        Err(e) => {
            println!("INVALID");
            eprintln!("{e}");
            exit(1);
        }
    };

    match mode.as_str() {
        "sat" => {
            let aag = match aiger::load(&cert_path) {
                Ok(a) => a,
                Err(e) => {
                    println!("INVALID");
                    eprintln!("{e}");
                    exit(1);
                }
            };
            let scratch = std::env::temp_dir();
            match sat::verify(&f, &aag, &solver, &scratch) {
                sat::Verdict::Valid => {
                    println!("VALID");
                    exit(0);
                }
                sat::Verdict::DepViolation(m) => {
                    println!("DEP-VIOLATION");
                    eprintln!("{m}");
                    exit(1);
                }
                sat::Verdict::Invalid(m) => {
                    println!("INVALID");
                    eprintln!("{m}");
                    exit(1);
                }
            }
        }
        "unsat" => {
            let steps = match frp::load(&cert_path) {
                Ok(s) => s,
                Err(e) => {
                    println!("INVALID");
                    eprintln!("{e}");
                    exit(1);
                }
            };
            match unsat::verify(&f, &steps) {
                unsat::Verdict::Valid => {
                    println!("VALID");
                    exit(0);
                }
                unsat::Verdict::Invalid(m) => {
                    println!("INVALID");
                    eprintln!("{m}");
                    exit(1);
                }
            }
        }
        m => {
            eprintln!("unknown mode '{m}'");
            exit(2);
        }
    }
}

fn default_solver() -> PathBuf {
    // Use the same fallback chain as the Python verifier (interface
    // contract), but resolve independently. Try PATH first.
    for name in ["kissat", "cadical", "satch"] {
        if let Ok(o) = std::process::Command::new("which").arg(name).output() {
            if o.status.success() {
                return PathBuf::from(String::from_utf8_lossy(&o.stdout).trim());
            }
        }
    }
    // Fall back to the in-tree builds. Locate the repo root by walking up.
    let mut here = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for _ in 0..6 {
        for cand in ["third_party/kissat/build/kissat", "third_party/satch/satch"] {
            let p = here.join(cand);
            if p.exists() {
                return p;
            }
        }
        if !here.pop() {
            break;
        }
    }
    PathBuf::from("kissat")
}
