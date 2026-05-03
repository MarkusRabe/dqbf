mod aiger;
mod formula;
mod parse;
mod proof;
mod rules;
mod search;

use search::{solve, Config, Verdict};
use std::fs;
use std::io::{Read, Write};
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    let mut path: Option<String> = None;
    let mut cfg = Config::default();
    let mut cert_path: Option<String> = None;
    let mut proof_path: Option<String> = None;
    let mut trace = false;
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--timeout" => {
                i += 1;
                cfg.timeout_s = args[i].parse().unwrap_or(10.0);
            }
            "--max-clauses" => {
                i += 1;
                cfg.max_clauses = args[i].parse().unwrap_or(50_000);
            }
            "--cert" => {
                i += 1;
                cert_path = Some(args[i].clone());
            }
            "--proof" => {
                i += 1;
                proof_path = Some(args[i].clone());
            }
            "--trace" => trace = true,
            s if !s.starts_with('-') => path = Some(s.to_string()),
            _ => {}
        }
        i += 1;
    }
    let text = match path {
        Some(p) => {
            if p.ends_with(".gz") {
                let bytes = fs::read(&p).expect("read");
                let mut d = flate2_decode(&bytes);
                let mut s = String::new();
                d.read_to_string(&mut s).expect("gunzip");
                s
            } else {
                fs::read_to_string(&p).expect("read")
            }
        }
        None => {
            let mut s = String::new();
            std::io::stdin().read_to_string(&mut s).expect("stdin");
            s
        }
    };
    cfg.extract_cert = cert_path.is_some();
    let f = match parse::parse(&text) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("parse error: {e}");
            return ExitCode::from(1);
        }
    };
    let out = solve(&f, &cfg);
    let (name, code) = match out.verdict {
        Verdict::Sat => ("SAT", 10),
        Verdict::Unsat => ("UNSAT", 20),
        Verdict::Unknown => ("UNKNOWN", 0),
    };
    println!("{name}");
    if trace {
        eprintln!("c {}", out.stats);
    }
    if let (Verdict::Sat, Some(cp), Some(sk)) = (&out.verdict, &cert_path, &out.skolem) {
        let mut w = fs::File::create(cp).expect("cert");
        aiger::write_skolem_aag(&mut w, &f, sk).expect("write aag");
    }
    if let (Verdict::Unsat, Some(pp), Some(pr)) = (&out.verdict, &proof_path, &out.proof) {
        let mut w = fs::File::create(pp).expect("proof");
        pr.write_json(&mut w).expect("write frp");
    }
    let _ = std::io::stdout().flush();
    ExitCode::from(code)
}

// Minimal gzip decoder via the system `gzip` to avoid a crate dep.
fn flate2_decode(bytes: &[u8]) -> impl Read {
    use std::process::{Command, Stdio};
    let mut child = Command::new("gzip")
        .arg("-dc")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("spawn gzip");
    child
        .stdin
        .take()
        .unwrap()
        .write_all(bytes)
        .expect("write gzip stdin");
    child.stdout.take().unwrap()
}
