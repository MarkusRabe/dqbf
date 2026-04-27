from __future__ import annotations

import sys

import click

from core import dqdimacs
from core.certificate import load_skolem
from provers.forkres.proof import load as load_proof
from tools.verify.sat import verify_skolem
from tools.verify.unsat import verify_proof


@click.group()
def main() -> None:
    pass


@main.command("sat")
@click.argument("formula", type=click.Path(exists=True))
@click.argument("cert", type=click.Path(exists=True))
def sat_cmd(formula: str, cert: str) -> None:
    f = dqdimacs.load(formula)
    sk = load_skolem(cert)
    ok = verify_skolem(f, sk)
    print("VALID" if ok else "INVALID")
    sys.exit(0 if ok else 1)


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
