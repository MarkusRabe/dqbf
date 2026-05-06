"""PolyBench/C equivalence pairs → DQBF.  See README.md for design.

Encoding A (memory-as-function) is the only one wired; encoding B
(UF-lifting) needs a `UF` op in `tools/progequiv2dqbf/isa.py` first.
"""

from __future__ import annotations

import argparse
import gzip
import json
from dataclasses import asdict
from pathlib import Path

from core.dqdimacs import dumps
from tools.progequiv2dqbf.encode import Config, encode_bounded
from tools.progequiv2dqbf.isa import parse

HERE = Path(__file__).parent
PROG = HERE / "programs"


# (kernel, P, Q, expected)  — expected derives from polyhedral legality:
# loop reversal/interchange with no carried dependence ⇒ "sat".
PAIRS: list[tuple[str, str, str, str]] = [
    ("jacobi1d_n4_rev", "jacobi1d_n4_ref.asm", "jacobi1d_n4_rev.asm", "sat"),
    # Stubs to fill: atax_n2_{ij,ji}, mvt_n2_{ref,fused}, gesummv_n2_{ref,unroll},
    # 2mm_n2_{ref,ikj}, jacobi1d_n4_fused (UNSAT — fusing both sweeps is illegal).
]

CONFIGS: list[Config] = [
    Config(word_bits=w, addr_bits=3, n_regs=4, bound=24, out_reg=0)
    for w in (3, 4, 6, 8)
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "instances"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for name, p_asm, q_asm, expected in PAIRS:
        P = parse((PROG / p_asm).read_text(), p_asm)
        Q = parse((PROG / q_asm).read_text(), q_asm)
        for cfg in CONFIGS:
            f = encode_bounded(P, Q, cfg, source=name)
            stem = f"polybench_{name}_w{cfg.word_bits}_k{cfg.bound}"
            (out / f"{stem}.dqdimacs.gz").write_bytes(
                gzip.compress(dumps(f).encode())
            )
            manifest.append(
                {
                    "path": f"{stem}.dqdimacs.gz",
                    "expected": expected,
                    "n_vars": f.n_vars,
                    "n_clauses": len(f.clauses),
                    "source": f"{p_asm} vs {q_asm}",
                    "config": asdict(cfg),
                }
            )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} instances → {out}")


if __name__ == "__main__":
    main()
