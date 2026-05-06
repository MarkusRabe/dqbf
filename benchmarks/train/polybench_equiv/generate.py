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
# loop reversal/interchange with no carried dependence ⇒ "sat"; with one ⇒ "unsat".
PAIRS: list[tuple[str, str, str, str]] = [
    ("jacobi1d_n4_rev", "jacobi1d_n4_ref.asm", "jacobi1d_n4_rev.asm", "sat"),
    ("copy_n4_bwd", "copy_n4_fwd.asm", "copy_n4_bwd.asm", "sat"),
    ("prefix_sum_n4_rev", "prefix_sum_n4_ref.asm", "prefix_sum_n4_rev.asm", "unsat"),
    # Stubs to fill: atax_n2_{ij,ji}, mvt_n2_{ref,fused}, gesummv_n2_{ref,unroll}
    # need a MUL/AND op in tools/progequiv2dqbf/isa.py first.
]

WORD_BITS = (3, 4, 6, 8, 12, 16, 24, 32)
VAR_CAP = 50_000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "mem_trace"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    skipped = 0
    for name, p_asm, q_asm, expected in PAIRS:
        P = parse((PROG / p_asm).read_text(), p_asm)
        Q = parse((PROG / q_asm).read_text(), q_asm)
        for w in WORD_BITS:
            cfg = Config(word_bits=w, addr_bits=3, n_regs=4, bound=24, out_reg=0)
            f = encode_bounded(P, Q, cfg, source=name)
            if f.n_vars > VAR_CAP:
                skipped += 1
                continue
            stem = f"polybench_{name}_w{cfg.word_bits:02d}_k{cfg.bound}"
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
    print(f"wrote {len(manifest)} instances → {out}/ ({skipped} skipped at >{VAR_CAP} vars)")


if __name__ == "__main__":
    main()
