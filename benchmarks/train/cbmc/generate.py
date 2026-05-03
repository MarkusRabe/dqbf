"""CBMC propositional CNF → DQDIMACS (no universals).

For each C source × unwind depth, run `cbmc --dimacs` to get the
propositional verification condition. The CNF is SAT iff the assertion
can fail at that unwind. We wrap it as DQDIMACS by inserting a single
`e 1..N 0` block (all existential, empty deps) — the degenerate
propositional case of DQBF. Ground truth comes from running cbmc
itself at the same unwind.

These exercise DQBF solvers on realistic program-verification CNF
structure. cbmc is registered as a `domain="cbmc"` cross-check solver
by the runner (it consumes the source `.c`, not the `.dqdimacs`).
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from pathlib import Path

import click

HERE = Path(__file__).resolve().parent
SRC = HERE / "sources"
OUT = HERE / "instances"

CBMC_FLAGS = ["--no-unwinding-assertions", "--bounds-check", "--div-by-zero-check"]


def cbmc_verdict(c: Path, unwind: int) -> str:
    """'unsat' (SUCCESSFUL), 'sat' (FAILED), or 'unknown'."""
    cp = subprocess.run(
        ["cbmc", str(c), "--unwind", str(unwind), *CBMC_FLAGS],
        capture_output=True,
        text=True,
    )
    if "VERIFICATION SUCCESSFUL" in cp.stdout:
        return "unsat"
    if "VERIFICATION FAILED" in cp.stdout:
        return "sat"
    return "unknown"


def cbmc_dimacs(c: Path, unwind: int) -> tuple[int, list[str]]:
    """Run cbmc --dimacs; return (n_vars, clause_lines)."""
    cp = subprocess.run(
        ["cbmc", str(c), "--unwind", str(unwind), *CBMC_FLAGS, "--dimacs"],
        capture_output=True,
        text=True,
    )
    n_vars = 0
    clauses: list[str] = []
    for ln in cp.stdout.splitlines():
        if ln.startswith("p cnf"):
            n_vars = int(ln.split()[2])
        elif ln.startswith("c ") or not ln.strip():
            continue
        elif ln[0] in "-0123456789":
            clauses.append(ln)
    return n_vars, clauses


@click.command()
@click.option("-K", "unwinds", default="5,20")
@click.option("--max-nvars", default=200_000)
def main(unwinds: str, max_nvars: int) -> None:
    if shutil.which("cbmc") is None:
        raise SystemExit("cbmc not found; install with: sudo apt-get install -y cbmc")
    OUT.mkdir(parents=True, exist_ok=True)
    ks = [int(x) for x in unwinds.split(",")]
    manifest = []
    seen: set[int] = set()
    for c in sorted(SRC.glob("*.c")):
        for k in ks:
            n_vars, clauses = cbmc_dimacs(c, k)
            if n_vars == 0 or n_vars > max_nvars:
                print(f"  skip {c.name} u={k}: n_vars={n_vars} (decided pre-SAT or too big)")
                continue
            h = hash((n_vars, tuple(clauses)))
            if h in seen:
                continue
            seen.add(h)
            expected = cbmc_verdict(c, k)
            stem = f"{c.stem}_u{k:03d}"
            with gzip.open(OUT / f"{stem}.dqdimacs.gz", "wt") as fp:
                fp.write(
                    f"c benchmarks/train/cbmc/generate.py source={c.name} "
                    f"unwind={k} cbmc_verdict={expected}\n"
                )
                fp.write(f"p cnf {n_vars} {len(clauses)}\n")
                fp.write("e " + " ".join(str(v) for v in range(1, n_vars + 1)) + " 0\n")
                fp.write("\n".join(clauses) + "\n")
            manifest.append(
                {
                    "path": f"{stem}.dqdimacs.gz",
                    "expected": expected,
                    "tags": ["cbmc", c.stem],
                    "params": {"unwind": k, "source": c.name},
                }
            )
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    sat = sum(1 for m in manifest if m["expected"] == "sat")
    unsat = sum(1 for m in manifest if m["expected"] == "unsat")
    print(
        f"wrote {len(manifest)} instances ({sat} sat / {unsat} unsat / "
        f"{len(manifest) - sat - unsat} unknown) to {OUT}/"
    )


if __name__ == "__main__":
    main()
