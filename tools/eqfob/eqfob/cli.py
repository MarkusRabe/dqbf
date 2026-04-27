from __future__ import annotations

import sys

import click

from core import dqdimacs
from tools.eqfob.eqfob.bitblast import bitblast
from tools.eqfob.eqfob.parse import parse
from tools.eqfob.eqfob.typecheck import check


@click.group()
def main() -> None:
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--out", type=click.Path(dir_okay=False), default="-")
@click.option("-D", "defs", multiple=True, help="override param: NAME=INT")
def compile(path: str, out: str, defs: tuple[str, ...]) -> None:
    overrides: dict[str, int] = {}
    for d in defs:
        k, v = d.split("=", 1)
        overrides[k] = int(v)
    p = parse(open(path).read())
    f = bitblast(check(p, overrides=overrides))
    text = dqdimacs.dumps(f)
    if out == "-":
        sys.stdout.write(text)
    else:
        with open(out, "w") as fh:
            fh.write(text)


if __name__ == "__main__":
    main()
