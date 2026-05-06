"""bmc_circuits: parametric sequential circuits × BMC bound × encoding.

Consolidated family — supersedes the old v1/v2/v3 + _succinct split.
27 circuits total:

- 11 with paired safe/bug variants (``circuits_v3``): expected is set
  by construction from the known reachability depth ``k_bad``.
- 16 single-variant (``circuits`` + ``circuits_v2``): expected =
  unknown (reachability of bad depends on N,k).

Each (circuit, N, k, variant) is emitted in **three** encodings:

- ``{name}/``           — unrolled (`encode`, O(k·|circ|) vars)
- ``succinct/{name}/``  — universal step-counter (`encode_succinct`,
                          O(|circ|+log k) vars; genuine DQBF)
- ``indinv/{name}/``    — inductive-invariant search (`encode_indinv`,
                          k-independent; SAT ⇔ property holds)

Default grid N∈{4,8,12,16,20,24,32} × k∈{8,24}: 532 unrolled +
532 succinct + 266 indinv = 1330 instances.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from core.formula import Formula
from tools.bmc2dqbf.circuits import REGISTRY
from tools.bmc2dqbf.circuits_v2 import REGISTRY_V2
from tools.bmc2dqbf.circuits_v3 import REGISTRY_V3
from tools.bmc2dqbf.encode import encode, encode_succinct
from tools.hwmc2dqbf_indinv.encode import encode_indinv_aig
from tools.pec2dqbf.aiger_seq import SeqAig, parse_seq_aag

WIDTHS = (4, 8, 12, 16, 20, 24, 32)
BOUNDS = (8, 24)

# Single-variant builders (v1+v2): bad-state reachability varies with N,k.
SINGLE = {**REGISTRY, **REGISTRY_V2}


def _expected(variant: str, k: int, k_bad: int | None) -> str:
    if variant == "safe":
        return "unsat"
    if variant == "bug":
        return "unknown" if k_bad is None else ("sat" if k >= k_bad else "unsat")
    return "unknown"


def _expected_indinv(variant: str) -> str:
    # Semantics flip: SAT = inductive invariant exists = property holds.
    if variant == "safe":
        return "sat"
    if variant == "bug":
        return "unsat"
    return "unknown"


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/bmc_circuits")
@click.option("-N", "widths", default=",".join(str(w) for w in WIDTHS))
@click.option("-K", "bounds", default=",".join(str(k) for k in BOUNDS))
@click.option("--max-vars", default=50_000)
@click.option("--max-per-circuit", default=0)
@click.option("--succinct/--no-succinct", default=True)
@click.option("--indinv/--no-indinv", default=True)
def main(
    out: str,
    widths: str,
    bounds: str,
    max_vars: int,
    max_per_circuit: int,
    succinct: bool,
    indinv: bool,
) -> None:
    base = Path(out)
    ws = [int(x) for x in widths.split(",")]
    ks = [int(x) for x in bounds.split(",")]
    encoders: list[tuple[str, Path]] = [("unrolled", base)]
    if succinct:
        encoders.append(("succinct", base / "succinct"))

    manifests: dict[tuple[str, str], list[dict]] = {}
    skipped: list[str] = []
    total = 0

    def _enc(seq: SeqAig, k: int, enc_name: str, src: str) -> Formula:
        if enc_name == "succinct":
            return encode_succinct(seq, k=k, source=src)
        return encode(seq, k=k, source=src)

    def emit(name: str, n: int, variant: str, aag: str, comment: str, k_bad: int | None) -> None:
        nonlocal total
        seq = parse_seq_aag(aag)
        suffix = f"_{variant}" if variant else ""
        src = f"{name}_n{n}{suffix}.aag"
        for enc_name, root in encoders:
            d = root / name
            d.mkdir(parents=True, exist_ok=True)
            if enc_name == "unrolled":
                (d / src).write_text(aag)
            mf = manifests.setdefault((enc_name, name), [])
            for k in ks:
                if max_per_circuit and len(mf) >= max_per_circuit:
                    break
                f = _enc(seq, k, enc_name, src)
                if f.n_vars > max_vars:
                    skipped.append(f"{enc_name}/{name} n={n} k={k} {variant} ({f.n_vars} vars)")
                    continue
                inst = f"{name}_n{n}_k{k:03d}{suffix}"
                with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                    fp.write(
                        f"c bmc_circuits/{name} enc={enc_name} N={n} k={k} "
                        f"variant={variant or '-'}: {comment}\n"
                    )
                    fp.write(dqdimacs.dumps(f))
                mf.append(
                    {
                        "path": f"{inst}.dqdimacs.gz",
                        "expected": _expected(variant, k, k_bad),
                        "tags": ["bmc_circuits", name, variant or "single", enc_name],
                        "params": {"N": n, "k": k, "variant": variant, "k_bad": k_bad},
                    }
                )
                total += 1
        if indinv:
            d = base / "indinv" / name
            d.mkdir(parents=True, exist_ok=True)
            try:
                fi = encode_indinv_aig(seq, source=src)
            except ValueError as e:
                skipped.append(f"indinv/{name} n={n} {variant} ({e})")
                return
            if fi.n_vars > max_vars:
                skipped.append(f"indinv/{name} n={n} {variant} ({fi.n_vars} vars)")
                return
            inst = f"{name}_n{n}_indinv{suffix}"
            with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                fp.write(
                    f"c bmc_circuits/{name} enc=indinv N={n} "
                    f"variant={variant or '-'}: {comment}\n"
                )
                fp.write(dqdimacs.dumps(fi))
            manifests.setdefault(("indinv", name), []).append(
                {
                    "path": f"{inst}.dqdimacs.gz",
                    "expected": _expected_indinv(variant),
                    "tags": ["bmc_circuits", name, variant or "single", "indinv"],
                    "params": {"N": n, "variant": variant},
                }
            )
            total += 1

    for name, fn in sorted(REGISTRY_V3.items()):
        for n in ws:
            for variant, bug in (("safe", False), ("bug", True)):
                aag, comment, k_bad = fn(n, bug)
                emit(name, n, variant, aag, comment, k_bad)
    for name, lfn in sorted(SINGLE.items()):
        for n in ws:
            aag, comment = lfn(n)
            emit(name, n, "", aag, comment, None)

    enc_root = {"unrolled": base, "succinct": base / "succinct", "indinv": base / "indinv"}
    for (enc_name, name), m in sorted(manifests.items()):
        (enc_root[enc_name] / name / "manifest.json").write_text(json.dumps(m, indent=2))
        print(f"{enc_name}/{name}: {len(m)} instances")

    print(f"total: {total} instances; {len(skipped)} skipped (>{max_vars} vars or error)")
    for s in skipped[:20]:
        print(f"  skip: {s}")
    if len(skipped) > 20:
        print(f"  ... +{len(skipped) - 20} more")


if __name__ == "__main__":
    main()
