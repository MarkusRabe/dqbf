from __future__ import annotations

import sys
from pathlib import Path

import click

from core import dqdimacs
from tools.ltlsynth2dqbf.encode import encode_tlsf
from tools.ltlsynth2dqbf.tlsf import TlsfNotSupported


@click.command()
@click.argument("tlsf", type=click.Path(exists=True, dir_okay=False))
@click.option("-n", "--n-states", type=int, default=2, help="state-bit budget")
@click.option("-k", "--unroll", type=int, default=4, help="trace length")
@click.option("-o", "--out", type=click.Path(), default=None)
def main(tlsf: str, n_states: int, unroll: int, out: str | None) -> None:
    text = Path(tlsf).read_text()
    try:
        f = encode_tlsf(text, n_states=n_states, k=unroll, source=Path(tlsf).name)
    except TlsfNotSupported as exc:
        print(f"unsupported TLSF feature: {exc}", file=sys.stderr)
        sys.exit(2)
    s = dqdimacs.dumps(f)
    if out:
        Path(out).write_text(s)
    else:
        sys.stdout.write(s)


if __name__ == "__main__":
    main()
