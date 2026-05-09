from __future__ import annotations

import json
import sys

import click

from tools.verify.formats import load_aag, load_dqdimacs, load_proof
from tools.verify.sat import decode_model, encode_verification, solve_cnf
from tools.verify.unsat import verify_proof


@click.group()
def main() -> None:
    pass


@main.command("sat")
@click.argument("formula", type=click.Path(exists=True))
@click.argument("cert_aag", type=click.Path(exists=True))
@click.option("-o", "--out", "cnf_out", type=click.Path(), required=True)
@click.option("--map", "map_out", type=click.Path(), default=None)
@click.option("--solve", "do_solve", is_flag=True, help="run a SAT solver and report VALID/INVALID")
def sat_cmd(formula: str, cert_aag: str, cnf_out: str, map_out: str | None, do_solve: bool) -> None:
    """Emit a DIMACS CNF whose UNSAT proves the AIGER Skolem cert valid."""
    # Fail-INVALID, never fail-silent: a malformed `.aag` or `.dqdimacs`
    # must surface as `INVALID`, not a stack trace.
    try:
        f = load_dqdimacs(formula)
        aig = load_aag(cert_aag)
        enc = encode_verification(f, aig)
    except Exception as e:
        print("INVALID", flush=True)
        print(f"verifier error: {e}", file=sys.stderr)
        sys.exit(1)
    enc.write_dimacs(cnf_out)
    if map_out:
        enc.write_map(map_out)
    if enc.dep_violations:
        for v in enc.dep_violations:
            print(f"DEP-VIOLATION {v}", file=sys.stderr)
        sys.exit(2)
    print(f"wrote {cnf_out}: {enc.n_vars} vars, {len(enc.clauses)} clauses")
    if not do_solve:
        print("run a SAT solver on it; UNSAT => certificate VALID")
        return
    is_sat, model = solve_cnf(enc.n_vars, enc.clauses)
    if is_sat is None:
        print("no SAT backend available (install 'python-sat' or put cadical/kissat on PATH)")
        sys.exit(3)
    if is_sat:
        print("INVALID")
        assert model is not None
        print(json.dumps(decode_model(model, enc.varmap)), file=sys.stderr)
        sys.exit(1)
    print("VALID")
    sys.exit(0)


@main.command("unsat")
@click.argument("formula", type=click.Path(exists=True))
@click.argument("proof", type=click.Path(exists=True))
def unsat_cmd(formula: str, proof: str) -> None:
    # Fail-INVALID, never fail-silent: a malformed/truncated proof
    # (e.g., a prover that hit its timeout mid-write) must surface as
    # `INVALID`, not as a stack trace. The error message goes to
    # stderr so the harness still sees the cause.
    try:
        f = load_dqdimacs(formula)
        p = load_proof(proof)
        ok = verify_proof(f, p)
    except Exception as e:
        # Flush stdout first so the verdict line precedes the error
        # message even when the caller merges stdout+stderr.
        print("INVALID", flush=True)
        print(f"verifier error: {e}", file=sys.stderr)
        sys.exit(1)
    print("VALID" if ok else "INVALID")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
