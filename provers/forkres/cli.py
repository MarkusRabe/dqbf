from __future__ import annotations

import sys

import click

from core import dqdimacs
from provers.forkres.search import SearchConfig, solve


@click.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False), required=False)
@click.option("--timeout", "timeout_s", type=float, default=10.0)
@click.option("--max-clauses", type=int, default=5000)
@click.option("--max-forks", type=int, default=32)
@click.option("--trace", is_flag=True)
def main(path: str | None, timeout_s: float, max_clauses: int, max_forks: int, trace: bool) -> None:
    text = open(path).read() if path else sys.stdin.read()
    f = dqdimacs.parse(text)
    cfg = SearchConfig(max_clauses=max_clauses, max_forks=max_forks, timeout_s=timeout_s)
    res, tr = solve(f, cfg)
    print(res.name)
    if trace:
        for s in tr.steps:
            print(f"c {s}")
    sys.exit(res.value)


if __name__ == "__main__":
    main()
