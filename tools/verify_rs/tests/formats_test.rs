//! Parser tests via the CLI (dqdimacs / aiger / frp).

use std::process::Command;

fn run_unsat(dq: &str, frp: &str) -> String {
    let dir = std::env::temp_dir();
    let n = std::process::id() as u64 + std::time::SystemTime::now().elapsed().unwrap_or_default().subsec_nanos() as u64;
    let dqp = dir.join(format!("fmt_{n}.dqdimacs"));
    let pf = dqp.with_extension("frp");
    std::fs::write(&dqp, dq).unwrap();
    std::fs::write(&pf, frp).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_dqbf-verify-rs"))
        .arg("unsat")
        .arg(&dqp)
        .arg(&pf)
        .output()
        .unwrap();
    let _ = std::fs::remove_file(&dqp);
    let _ = std::fs::remove_file(&pf);
    String::from_utf8_lossy(&out.stdout).trim().to_string()
}

#[test]
fn dq_empty_file() {
    assert_eq!(run_unsat("", "[]"), "INVALID");
}

#[test]
fn dq_no_zero_terminator() {
    assert_eq!(run_unsat("p cnf 2 1\na 1 0\nd 2 1 0\n1 2\n", "[]"), "INVALID");
}

#[test]
fn dq_d_unknown_universal() {
    assert_eq!(run_unsat("p cnf 2 0\nd 2 1 0\n", "[]"), "INVALID");
}

#[test]
fn dq_var_overflow() {
    assert_eq!(
        run_unsat("p cnf 2 1\na 1 0\nd 2 1 0\n99 0\n", "[]"),
        "INVALID"
    );
}

#[test]
fn dq_e_line_tracks_universals() {
    // ∀1 ∃2 ∀3 ∃4: e2 has dep={1}, e4 has dep={1,3}.
    let dq = "p cnf 4 2\na 1 0\ne 2 0\na 3 0\ne 4 0\n3 4 0\n3 -4 0\n";
    // ured drop 3 from (3,4): 3 ∈ dep(4) → INVALID.
    let frp = r#"[
      {"clause":[3,4],"rule":"axiom"},
      {"clause":[4],"rule":"ured","premises":[0]}
    ]"#;
    assert_eq!(run_unsat(dq, frp), "INVALID");
    // ured drop 1 from a clause with only 4: 1 ∈ dep(4) → INVALID.
    // ured drop 3 from a clause with only 2: 3 ∉ dep(2) → would need
    // 3 in the clause first.
}

#[test]
fn frp_trailing_garbage() {
    assert_eq!(
        run_unsat("p cnf 2 1\na 1 0\nd 2 1 0\n1 2 0\n", "[] extra"),
        "INVALID"
    );
}

#[test]
fn frp_negative_premise() {
    assert_eq!(
        run_unsat(
            "p cnf 2 1\na 1 0\nd 2 1 0\n1 2 0\n",
            r#"[{"clause":[1],"rule":"res","premises":[-1,0],"pivot":2}]"#
        ),
        "INVALID"
    );
}
