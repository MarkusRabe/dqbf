from __future__ import annotations

import json
import sys

import click

from core import dqdimacs
from core.aiger import load_aag
from core.proof_trace import load as load_proof
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
    f = dqdimacs.load(formula)
    aig = load_aag(cert_aag)
    enc = encode_verification(f, aig)
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
    f = dqdimacs.load(formula)
    p = load_proof(proof)
    ok = verify_proof(f, p)
    print("VALID" if ok else "INVALID")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
