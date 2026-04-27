from __future__ import annotations

import sys

import click

from core import dqdimacs
from core.aiger import skolem_to_aag
from core.certificate import save_skolem
from provers.forkres.proof import save as save_proof
from provers.forkres.search import Result, SearchConfig, solve


@click.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False), required=False)
@click.option("--timeout", "timeout_s", type=float, default=10.0)
@click.option("--max-clauses", type=int, default=5000)
@click.option("--max-forks", type=int, default=32)
@click.option("--cert", "cert_path", type=click.Path(), default=None)
@click.option("--proof", "proof_path", type=click.Path(), default=None)
@click.option("--trace", is_flag=True)
def main(
    path: str | None,
    timeout_s: float,
    max_clauses: int,
    max_forks: int,
    cert_path: str | None,
    proof_path: str | None,
    trace: bool,
) -> None:
    f = dqdimacs.load(path) if path else dqdimacs.parse(sys.stdin.read())
    cfg = SearchConfig(
        max_clauses=max_clauses,
        max_forks=max_forks,
        timeout_s=timeout_s,
        extract_cert=cert_path is not None,
    )
    out = solve(f, cfg)
    print(out.result.name)
    if trace:
        for s in out.log:
            print(f"c {s}")
    if out.result is Result.SAT and cert_path and out.skolem:
        save_skolem(cert_path, f, out.skolem)
        with open(cert_path + ".aag", "w") as fp:
            fp.write(skolem_to_aag(f, out.skolem))
    if out.result is Result.UNSAT and proof_path and out.proof:
        save_proof(proof_path, out.proof)
    sys.exit(out.result.value)


if __name__ == "__main__":
    main()
