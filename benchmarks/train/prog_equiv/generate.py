"""Generate prog_equiv instances: each program pair × (W, A, K) grid.

Stub generator — the program corpus is three hand-written pairs and
the parameter grid is small. Expand once `encode_bounded` is audited.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.progequiv2dqbf.encode import Config, encode_bounded
from tools.progequiv2dqbf.isa import load

HERE = Path(__file__).resolve().parent
PROGS = HERE / "programs"

PAIRS: list[tuple[str, str, str]] = [
    ("swap_tmp", "swap_tmp", "sat"),  # self-pair: trivially equivalent
    ("swap_tmp", "swap_xor", "sat"),
    ("sum_iter", "sum_unroll", "unknown"),
    ("memcpy_fwd", "memcpy_bwd", "unknown"),
]

GRID: list[tuple[int, int, int]] = [
    (1, 1, 4),
    (2, 2, 4),
    (2, 2, 8),
    (2, 2, 16),
    (4, 3, 8),
    (4, 3, 16),
]


@click.command()
@click.option("--out", type=click.Path(), default=str(HERE / "mem_trace"))
def main(out: str) -> None:
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for pn, qn, expected in PAIRS:
        p = load(PROGS / f"{pn}.asm")
        q = load(PROGS / f"{qn}.asm")
        for w, a, k in GRID:
            cfg = Config(word_bits=w, addr_bits=a, n_regs=4, bound=k)
            f = encode_bounded(p, q, cfg, source=f"{pn}__{qn}")
            stem = f"pe_{pn}__{qn}_w{w}_a{a}_k{k:03d}"
            with gzip.open(d / f"{stem}.dqdimacs.gz", "wt") as fp:
                fp.write(dqdimacs.dumps(f))
            manifest.append(
                {
                    "path": f"{stem}.dqdimacs.gz",
                    "expected": expected,
                    "tags": ["prog_equiv", pn, qn, "bounded"],
                    "params": {"W": w, "A": a, "K": k},
                }
            )
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"prog_equiv: {len(manifest)} instances → {d}/")


if __name__ == "__main__":
    main()
