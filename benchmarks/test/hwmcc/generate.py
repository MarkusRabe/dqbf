"""Encode HWMCC'20 AIGER circuits as DQBF for the test set.

Mirrors `benchmarks/train/bmc_circuits/generate.py`'s three encodings:

- `unrolled/{name}/`  — k explicit BMC steps (`encode`)
- `succinct/{name}/`  — universal step-counter (`encode_succinct`,
                        genuine DQBF, O(|circ|+log k) vars)
- `inductive/{name}/` — inductive-invariant search (`encode_indinv_aig`,
                        k-independent; SAT ⇔ a 1-step inductive
                        invariant exists)

Source: HWMCC'20 bit-vector AIGER (run `download.sh` first; not
committed). `generate.py` picks the `--n-smallest` circuits by AIGER
header `M` (proxy for circuit size), converts binary `.aig` → ASCII
`.aag` via `third_party/aigtoaig`, and emits each in the three
encodings × `--bounds`.

`expected` is from the official HWMCC'20 per-instance results
(`hwmcc20-bv-all.csv`, sha256 pinned in `download.sh`):

- HWMCC `uns` (bad unreachable) → unrolled/succinct `unsat` at any k.
- HWMCC `sat` with bound `b` → unrolled/succinct `sat` for k≥b, `unsat`
  for k<b; `unknown` if the SAT bound isn't reported.
- inductive: `sat` (counterexample exists) → `unsat` (definitely no
  invariant). `uns` → `unknown` — a globally-safe property need not
  have a *1-step* inductive invariant, so we don't claim `sat`.
- HWMCC `unknown` (no MC solved it) → `unknown`.

Usage:
    bash benchmarks/test/hwmcc/download.sh   # fetch ~11 MB archive
    python -m benchmarks.test.hwmcc.generate
"""

from __future__ import annotations

import csv
import gzip
import json
import subprocess
import sys
from pathlib import Path

import click

from core import dqdimacs
from tools.bmc2dqbf.encode import encode, encode_succinct
from tools.hwmc2dqbf_indinv.encode import encode_indinv_aig
from tools.pec2dqbf.aiger_seq import parse_seq_aag

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AIGTOAIG = ROOT / "third_party" / "aigtoaig"
INSTANCES = HERE / "instances"
RESULTS_CSV = ROOT / "benchmarks" / "_downloads" / "hwmcc20-bv-all.csv"


def _load_results() -> dict[str, tuple[str, int | None]]:
    """Parse the official HWMCC'20 results CSV → {name: (verdict, sat_bound)}.

    `verdict` is one of `sat` / `uns` / `unknown` (HWMCC's vocabulary).
    `sat_bound` is the smallest reported BMC bound at which any model
    checker found a counterexample, or `None` if not reported.
    """
    out: dict[str, tuple[str, int | None]] = {}
    if not RESULTS_CSV.exists():
        print(f"warning: {RESULTS_CSV} missing; all expected=unknown", file=sys.stderr)
        return out
    with RESULTS_CSV.open() as f:
        rdr = csv.reader(f, delimiter=";")
        next(rdr)  # header
        for row in rdr:
            name = row[0]
            sats: list[int] = []
            unss = 0
            for i in range(1, len(row), 6):
                if i + 2 >= len(row):
                    break
                status, bound = row[i + 1], row[i + 2]
                if status == "sat":
                    try:
                        b = int(bound)
                    except ValueError:
                        b = -1
                    if b >= 0:
                        sats.append(b)
                    else:
                        sats.append(-1)
                elif status == "uns":
                    unss += 1
            if sats:
                bs = [b for b in sats if b >= 0]
                out[name] = ("sat", min(bs) if bs else None)
            elif unss:
                out[name] = ("uns", None)
            else:
                out[name] = ("unknown", None)
    return out


def _expected(verdict: str, sat_bound: int | None, k: int, kind: str) -> str:
    if kind == "inductive":
        if verdict == "sat":
            return "unsat"  # counterexample → no inductive invariant
        return "unknown"  # safe ≠ 1-step-inductive
    # unrolled / succinct (BMC at bound k):
    if verdict == "uns":
        return "unsat"
    if verdict == "sat":
        if sat_bound is None:
            return "unknown"
        return "sat" if k >= sat_bound else "unsat"
    return "unknown"


def _aag_text(aig: Path) -> str:
    """Binary `.aig` → ASCII `.aag` text. `aigtoaig` only writes ASCII
    when the output filename ends in `.aag`, so we go through a temp
    file rather than `/dev/stdout`."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".aag", delete=False) as tf:
        out = Path(tf.name)
    try:
        subprocess.run([str(AIGTOAIG), str(aig), str(out)], check=True, capture_output=True)
        return out.read_text()
    finally:
        out.unlink(missing_ok=True)


def _aig_size(aig: Path) -> int:
    """The AIGER header field `M` (max var index) as a circuit-size proxy."""
    head = aig.open("rb").read(64).split(b"\n", 1)[0].decode(errors="replace")
    parts = head.split()
    try:
        return int(parts[1])
    except (IndexError, ValueError):
        return 1 << 30


@click.command()
@click.option("--out", type=click.Path(), default=str(HERE))
@click.option("--n-smallest", default=50, help="how many circuits (smallest first)")
@click.option("-K", "bounds", default="4,8,16")
@click.option("--max-vars", default=80_000, help="skip encodings bigger than this")
def main(out: str, n_smallest: int, bounds: str, max_vars: int) -> None:
    base = Path(out)
    ks = [int(x) for x in bounds.split(",")]
    aigs = sorted(INSTANCES.rglob("*.aig"), key=_aig_size)[:n_smallest]
    if not aigs:
        print("no .aig under instances/ — run download.sh first", file=sys.stderr)
        sys.exit(1)
    results = _load_results()
    manifests: dict[tuple[str, str], list[dict]] = {}
    skipped: list[str] = []
    total = 0

    for aig in aigs:
        name = aig.stem
        verdict, sat_bound = results.get(name, ("unknown", None))
        try:
            aag_text = _aag_text(aig)
            seq = parse_seq_aag(aag_text)
        except Exception as e:  # noqa: BLE001 - log + skip per-circuit
            skipped.append(f"{name}: {e}")
            continue
        pkey = f"hwmcc:{name}"
        comment = f"HWMCC20 {name} (M={_aig_size(aig)}, hwmcc20-result={verdict})"
        # unrolled + succinct at each k.
        for enc_name, enc_fn in (("unrolled", encode), ("succinct", encode_succinct)):
            d = base / enc_name / name
            d.mkdir(parents=True, exist_ok=True)
            if enc_name == "unrolled":
                # The .aag asset goes here — _find_source_aag glob's
                # *unrolled/{name}/*.aag (sibling-variant fallback for
                # succinct/inductive). abc-bmc/abc-pdr also read it.
                (d / f"{name}.aag").write_text(aag_text)
            mf = manifests.setdefault((enc_name, name), [])
            for k in ks:
                try:
                    f = enc_fn(seq, k=k, source=f"{name}.aag")
                except Exception as e:  # noqa: BLE001 - log + skip per-encoding
                    skipped.append(f"{enc_name}/{name} k={k}: {e}")
                    continue
                if f.n_vars > max_vars:
                    skipped.append(f"{enc_name}/{name} k={k}: {f.n_vars} vars > cap")
                    continue
                inst = f"{name}_k{k:03d}"
                with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                    fp.write(f"c hwmcc/{name} enc={enc_name} k={k}: {comment}\n")
                    fp.write(dqdimacs.dumps(f))
                mf.append(
                    {
                        "path": f"{inst}.dqdimacs.gz",
                        "expected": _expected(verdict, sat_bound, k, enc_name),
                        "problem_key": pkey,
                        "source_aag": f"{name}.aag",
                        "tags": ["hwmcc", name, enc_name],
                        "params": {"k": k, "hwmcc20_verdict": verdict, "sat_bound": sat_bound},
                    }
                )
                total += 1
        # inductive (one instance, k-independent).
        d = base / "inductive" / name
        d.mkdir(parents=True, exist_ok=True)
        try:
            fi = encode_indinv_aig(seq, source=f"{name}.aag")
        except Exception as e:  # noqa: BLE001
            skipped.append(f"inductive/{name}: {e}")
            fi = None
        if fi is not None and fi.n_vars <= max_vars:
            inst = f"{name}_indinv"
            with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                fp.write(f"c hwmcc/{name} enc=inductive: {comment}\n")
                fp.write(dqdimacs.dumps(fi))
            manifests.setdefault(("inductive", name), []).append(
                {
                    "path": f"{inst}.dqdimacs.gz",
                    "expected": _expected(verdict, sat_bound, 0, "inductive"),
                    "problem_key": pkey,
                    "source_aag": f"{name}.aag",
                    # DQBF SAT = invariant exists = bad unreachable, which
                    # abc-* on the .aag reports as UNSAT.
                    "source_polarity": "inverted",
                    "tags": ["hwmcc", name, "inductive"],
                    "params": {"hwmcc20_verdict": verdict, "sat_bound": sat_bound},
                }
            )
            total += 1
        elif fi is not None:
            skipped.append(f"inductive/{name}: {fi.n_vars} vars > cap")

    for (enc_name, name), mf in manifests.items():
        d = base / enc_name / name
        (d / "manifest.json").write_text(json.dumps(mf, indent=2) + "\n")
    print(f"wrote {total} test instances ({len(aigs)} circuits, {len(skipped)} skipped)")
    if skipped:
        print(f"  skipped: {skipped[:5]}{' …' if len(skipped) > 5 else ''}")


if __name__ == "__main__":
    main()
