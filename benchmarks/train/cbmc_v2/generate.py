"""cbmc_v2: paired ok/bug C-algorithm benchmarks under two encodings.

Twelve single-loop algorithms, each in correct (`_ok`) and buggy
(`_bug`) variants, swept over bit-width and BMC bound. Every (family,
variant, width, bound) is emitted under **both** encodings:

  flat/      cbmc --dimacs on the rendered C source → all-existential
             DQDIMACS (degenerate, no universals). Ground truth from
             running cbmc itself.
  succinct/  the same algorithm built directly as sequential AIGER
             (`tools.cbmc2dqbf.circuits`) and passed through
             `encode_succinct` — latches become ∃-functions of a
             universal step counter, so the result is genuine DQBF.
             Ground truth is the analytic `expected` from the circuit
             registry, cross-checked at small width by
             `tools/cbmc2dqbf/circuits_test.py`.

The two encodings are **equisatisfiable by construction**: the AIGER
circuit and the C source implement the same algorithm bit-for-bit.
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from core import dqdimacs
from tools.bmc2dqbf.encode import encode_succinct
from tools.cbmc2dqbf.c_sources import render
from tools.cbmc2dqbf.circuits import expected_at
from tools.cbmc2dqbf.transition import families, seq_aig_for

HERE = Path(__file__).resolve().parent
OUT = HERE / "instances"

WIDTHS = (4, 6, 8)
BOUNDS = (8, 16, 32)
CBMC_FLAGS = ["--no-unwinding-assertions"]


def _cbmc_dimacs(src: str, unwind: int) -> tuple[int, list[str], str]:
    with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as fh:
        fh.write(src)
        c = fh.name
    cp_v = subprocess.run(
        ["cbmc", c, "--unwind", str(unwind), *CBMC_FLAGS],
        capture_output=True,
        text=True,
    )
    verdict = (
        "unsat"
        if "VERIFICATION SUCCESSFUL" in cp_v.stdout
        else "sat"
        if "VERIFICATION FAILED" in cp_v.stdout
        else "unknown"
    )
    cp_d = subprocess.run(
        ["cbmc", c, "--unwind", str(unwind), *CBMC_FLAGS, "--dimacs"],
        capture_output=True,
        text=True,
    )
    Path(c).unlink(missing_ok=True)
    n_vars = 0
    clauses: list[str] = []
    for ln in cp_d.stdout.splitlines():
        if ln.startswith("p cnf"):
            n_vars = int(ln.split()[2])
        elif ln and ln[0] in "-0123456789":
            clauses.append(ln)
    return n_vars, clauses, verdict


@click.command()
@click.option("-N", "widths", default=",".join(str(w) for w in WIDTHS))
@click.option("-K", "bounds", default=",".join(str(k) for k in BOUNDS))
@click.option("--max-nvars", default=400_000)
@click.option(
    "--mode",
    type=click.Choice(["flat", "succinct", "both"]),
    default="both",
)
def main(widths: str, bounds: str, max_nvars: int, mode: str) -> None:
    if mode in ("flat", "both") and shutil.which("cbmc") is None:
        raise SystemExit("cbmc not on PATH (needed for --mode flat)")
    ws = [int(x) for x in widths.split(",")]
    ks = [int(x) for x in bounds.split(",")]
    (OUT / "flat").mkdir(parents=True, exist_ok=True)
    (OUT / "succinct").mkdir(parents=True, exist_ok=True)
    m_flat: list[dict] = []
    m_succ: list[dict] = []
    for name in families():
        for bug in (False, True):
            tag = "bug" if bug else "ok"
            for n in ws:
                for k in ks:
                    stem = f"{name}_{tag}_n{n}_k{k:03d}"
                    if mode in ("succinct", "both"):
                        seq, comment = seq_aig_for(name, n, bug)
                        f = encode_succinct(seq, k=k, source=f"cbmc_v2:{stem}")
                        if f.n_vars <= max_nvars:
                            with gzip.open(OUT / "succinct" / f"{stem}.dqdimacs.gz", "wt") as fp:
                                fp.write(f"c cbmc_v2/succinct {comment} bound={k}\n")
                                fp.write(dqdimacs.dumps(f))
                            m_succ.append(
                                {
                                    "path": f"{stem}.dqdimacs.gz",
                                    "expected": expected_at(name, n, bug, k),
                                    "tags": ["cbmc_v2", "succinct", name, tag],
                                    "params": {"family": name, "bug": bug, "n": n, "k": k},
                                }
                            )
                    if mode in ("flat", "both"):
                        src = render(name, bug, bits=n)
                        nv, cls, verdict = _cbmc_dimacs(src, unwind=k)
                        if 0 < nv <= max_nvars:
                            with gzip.open(OUT / "flat" / f"{stem}.dqdimacs.gz", "wt") as fp:
                                fp.write(
                                    f"c cbmc_v2/flat {name} bug={bug} bits={n} unwind={k} "
                                    f"cbmc_verdict={verdict}\n"
                                )
                                fp.write(f"p cnf {nv} {len(cls)}\n")
                                fp.write("e " + " ".join(str(v) for v in range(1, nv + 1)) + " 0\n")
                                fp.write("\n".join(cls) + "\n")
                            m_flat.append(
                                {
                                    "path": f"{stem}.dqdimacs.gz",
                                    "expected": verdict,
                                    "tags": ["cbmc_v2", "flat", name, tag],
                                    "params": {"family": name, "bug": bug, "n": n, "k": k},
                                }
                            )
    if mode in ("flat", "both"):
        (OUT / "flat" / "manifest.json").write_text(json.dumps(m_flat, indent=2))
        s = sum(1 for m in m_flat if m["expected"] == "sat")
        u = sum(1 for m in m_flat if m["expected"] == "unsat")
        print(f"flat:     {len(m_flat)} instances ({s} sat / {u} unsat) → {OUT / 'flat'}/")
    if mode in ("succinct", "both"):
        (OUT / "succinct" / "manifest.json").write_text(json.dumps(m_succ, indent=2))
        s = sum(1 for m in m_succ if m["expected"] == "sat")
        u = sum(1 for m in m_succ if m["expected"] == "unsat")
        print(f"succinct: {len(m_succ)} instances ({s} sat / {u} unsat) → {OUT / 'succinct'}/")


if __name__ == "__main__":
    main()
