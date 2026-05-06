"""cbmc: C-program verification benchmarks under four encodings.

Consolidated family — supersedes the old `cbmc/` (handwritten sources)
+ `cbmc_v2/` (paired ok/bug algorithms) split.

| dir | encoding | quantifier shape | expected from |
|---|---|---|---|
| ``handwritten/`` | `cbmc --dimacs` on static `.c` sources | all-∃ | cbmc verdict |
| ``flat/`` | `cbmc --dimacs` on rendered `c_sources` | all-∃ | cbmc verdict |
| ``succinct/`` | `seq_aig_for` → `encode_succinct` | ∀t,t' ∃ latch(t) | analytic, cross-checked |
| ``inductive/`` | `seq_aig_for` → `encode_indinv` | ∀s,i,s' ∃ inv(s) | construction (ok→sat) |

For BMC encodings (handwritten/flat/succinct), SAT ⇔ assertion can
fail at that unwind. For ``inductive/`` the **semantics flip**: SAT ⇔
inductive invariant exists ⇔ property holds.

The handwritten sources are flat-DIMACS only (CBMC 5.12 emits no SSA
names, so post-hoc step extraction is not tractable); the algorithm
registry exposes the transition system as `SeqAig`, so the same corpus
feeds all of succinct/indinv.
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
from tools.hwmc2dqbf_indinv.encode import encode_indinv_aig

HERE = Path(__file__).resolve().parent
SRC = HERE / "sources"

VARIANTS = ("handwritten", "flat", "succinct", "inductive")

WIDTHS = (4, 6, 8)
BOUNDS = (8, 16, 32)
HW_UNWINDS = (5, 20)
CBMC_FLAGS = ["--no-unwinding-assertions"]
HW_FLAGS = ["--no-unwinding-assertions", "--bounds-check", "--div-by-zero-check"]


def _cbmc_dimacs(
    src: str, c_path: Path | None, unwind: int, flags: list[str]
) -> tuple[int, list[str], str]:
    """Run cbmc on either inline source or a file; return (n_vars, clauses, verdict)."""
    tmp: Path | None = None
    if c_path is None:
        fh = tempfile.NamedTemporaryFile("w", suffix=".c", delete=False)
        fh.write(src)
        fh.close()
        tmp = c_path = Path(fh.name)
    cp_v = subprocess.run(
        ["cbmc", str(c_path), "--unwind", str(unwind), *flags],
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
        ["cbmc", str(c_path), "--unwind", str(unwind), *flags, "--dimacs"],
        capture_output=True,
        text=True,
    )
    if tmp is not None:
        tmp.unlink(missing_ok=True)
    n_vars = 0
    clauses: list[str] = []
    for ln in cp_d.stdout.splitlines():
        if ln.startswith("p cnf"):
            n_vars = int(ln.split()[2])
        elif ln and ln[0] in "-0123456789":
            clauses.append(ln)
    return n_vars, clauses, verdict


def _write_flat(out: Path, header: str, n_vars: int, clauses: list[str]) -> None:
    with gzip.open(out, "wt") as fp:
        fp.write(header)
        fp.write(f"p cnf {n_vars} {len(clauses)}\n")
        fp.write("e " + " ".join(str(v) for v in range(1, n_vars + 1)) + " 0\n")
        fp.write("\n".join(clauses) + "\n")


@click.command()
@click.option("-N", "widths", default=",".join(str(w) for w in WIDTHS))
@click.option("-K", "bounds", default=",".join(str(k) for k in BOUNDS))
@click.option("--max-nvars", default=400_000)
@click.option("--mode", type=click.Choice([*VARIANTS, "all"]), default="all")
def main(widths: str, bounds: str, max_nvars: int, mode: str) -> None:
    need_cbmc = mode in ("handwritten", "flat", "all")
    if need_cbmc and shutil.which("cbmc") is None:
        raise SystemExit("cbmc not on PATH (needed for handwritten/flat modes)")
    ws = [int(x) for x in widths.split(",")]
    ks = [int(x) for x in bounds.split(",")]
    for sub in VARIANTS:
        (HERE / sub).mkdir(parents=True, exist_ok=True)
    m: dict[str, list[dict]] = {sub: [] for sub in VARIANTS}

    if mode in ("handwritten", "all"):
        seen: set[int] = set()
        for c in sorted(SRC.glob("*.c")):
            for k in HW_UNWINDS:
                nv, cls, verdict = _cbmc_dimacs("", c, k, HW_FLAGS)
                if nv == 0 or nv > max_nvars:
                    continue
                h = hash((nv, tuple(cls)))
                if h in seen:
                    continue
                seen.add(h)
                stem = f"{c.stem}_u{k:03d}"
                _write_flat(
                    HERE / "handwritten" / f"{stem}.dqdimacs.gz",
                    f"c cbmc/handwritten source={c.name} unwind={k} cbmc_verdict={verdict}\n",
                    nv,
                    cls,
                )
                m["handwritten"].append(
                    {
                        "path": f"{stem}.dqdimacs.gz",
                        "expected": verdict,
                        "problem_key": f"cbmc:{c.stem}:hw:prop",
                        "tags": ["cbmc", "handwritten", c.stem],
                        "params": {"unwind": k, "source": c.name},
                    }
                )

    for name in families():
        for bug in (False, True):
            tag = "bug" if bug else "ok"
            for n in ws:
                seq, comment = seq_aig_for(name, n, bug)
                pkey = f"cbmc:{name}:{n}:{tag}"
                if mode in ("inductive", "all"):
                    fi = encode_indinv_aig(seq, source=f"cbmc/{name}_{tag}_n{n}")
                    if fi.n_vars <= max_nvars:
                        stem = f"{name}_{tag}_n{n}_indinv"
                        with gzip.open(HERE / "inductive" / f"{stem}.dqdimacs.gz", "wt") as fp:
                            fp.write(f"c cbmc/indinv {comment}\n")
                            fp.write(dqdimacs.dumps(fi))
                        m["inductive"].append(
                            {
                                "path": f"{stem}.dqdimacs.gz",
                                "expected": "unsat" if bug else "sat",
                                "problem_key": pkey,
                                "source_polarity": "inverted",
                                "tags": ["cbmc", "inductive", name, tag],
                                "params": {"family": name, "bug": bug, "n": n},
                            }
                        )
                for k in ks:
                    stem = f"{name}_{tag}_n{n}_k{k:03d}"
                    if mode in ("succinct", "all"):
                        f = encode_succinct(seq, k=k, source=f"cbmc/{stem}")
                        if f.n_vars <= max_nvars:
                            with gzip.open(HERE / "succinct" / f"{stem}.dqdimacs.gz", "wt") as fp:
                                fp.write(f"c cbmc/succinct {comment} bound={k}\n")
                                fp.write(dqdimacs.dumps(f))
                            m["succinct"].append(
                                {
                                    "path": f"{stem}.dqdimacs.gz",
                                    "expected": expected_at(name, n, bug, k),
                                    "problem_key": pkey,
                                    "tags": ["cbmc", "succinct", name, tag],
                                    "params": {"family": name, "bug": bug, "n": n, "k": k},
                                }
                            )
                    if mode in ("flat", "all"):
                        c_src = render(name, bug, bits=n)
                        nv, cls, verdict = _cbmc_dimacs(c_src, None, k, CBMC_FLAGS)
                        if 0 < nv <= max_nvars:
                            hdr = (
                                f"c cbmc/flat {name} bug={bug} bits={n} "
                                f"unwind={k} cbmc_verdict={verdict}\n"
                            )
                            _write_flat(HERE / "flat" / f"{stem}.dqdimacs.gz", hdr, nv, cls)
                            m["flat"].append(
                                {
                                    "path": f"{stem}.dqdimacs.gz",
                                    "expected": verdict,
                                    "problem_key": pkey,
                                    "tags": ["cbmc", "flat", name, tag],
                                    "params": {"family": name, "bug": bug, "n": n, "k": k},
                                }
                            )

    for sub, mf in m.items():
        if not mf:
            continue
        (HERE / sub / "manifest.json").write_text(json.dumps(mf, indent=2))
        s = sum(1 for x in mf if x["expected"] == "sat")
        u = sum(1 for x in mf if x["expected"] == "unsat")
        print(f"{sub}: {len(mf)} instances ({s} sat / {u} unsat) → {HERE / sub}/")


if __name__ == "__main__":
    main()
