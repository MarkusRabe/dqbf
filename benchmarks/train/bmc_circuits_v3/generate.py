"""bmc_circuits_v3: scaled widths/bounds, new circuit types, safe/bug pairs.

Compared to v1/v2:

- 11 new circuit types (traffic, crc, lzc, barrel, bcd_ctr, debounce,
  spi_ctrl, prio_enc, parity_pipe, updown, hamming).
- Widths swept over {4,8,12,16,20,24,32}; bounds over {8,16,24}.
- Every (circuit, n) emits a *safe* and *bug* variant. Safe is provably
  UNSAT for all k; bug has a constructed ``k_bad`` so ``expected`` is
  derived (sat if k≥k_bad else unsat) without running a solver.
- Instances over ``--max-vars`` (default 50k) are skipped.
- All v1+v2 circuits are also regenerated at this grid under
  ``legacy_*/`` (safe-only — those builders take no bug flag), so v3 is
  a strict superset of the earlier families at the same width sweep.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from tools.bmc2dqbf.circuits import REGISTRY
from tools.bmc2dqbf.circuits_v2 import REGISTRY_V2
from tools.bmc2dqbf.circuits_v3 import REGISTRY_V3
from tools.bmc2dqbf.encode import encode
from tools.pec2dqbf.aiger_seq import parse_seq_aag

try:  # sibling agent's encoder; emit _indinv variants if available
    from tools.hwmc2dqbf_indinv.encode import encode_indinv_aig as _encode_indinv
except ImportError:
    _encode_indinv = None  # type: ignore[assignment]

WIDTHS = (4, 8, 12, 16, 20, 24, 32)
BOUNDS = (8, 24)


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/bmc_circuits_v3")
@click.option("-N", "widths", default=",".join(str(w) for w in WIDTHS))
@click.option("-K", "bounds", default=",".join(str(k) for k in BOUNDS))
@click.option("--max-vars", default=50_000, help="skip instances above this size")
@click.option("--max-per-circuit", default=0, help="cap instances per circuit dir (0 = none)")
@click.option("--indinv/--no-indinv", default=False, help="also emit inductive-invariant variants")
def main(
    out: str,
    widths: str,
    bounds: str,
    max_vars: int,
    max_per_circuit: int,
    indinv: bool,
) -> None:
    base = Path(out)
    ws = [int(x) for x in widths.split(",")]
    ks = [int(x) for x in bounds.split(",")]
    total = 0
    skipped: list[str] = []
    do_indinv = indinv and _encode_indinv is not None

    for name, fn in sorted(REGISTRY_V3.items()):
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        manifest: list[dict] = []
        for n in ws:
            for variant, bug in (("safe", False), ("bug", True)):
                aag, comment, k_bad = fn(n, bug)
                (d / f"{name}_n{n}_{variant}.aag").write_text(aag)
                seq = parse_seq_aag(aag)
                for k in ks:
                    if max_per_circuit and len(manifest) >= max_per_circuit:
                        break
                    f = encode(seq, k=k, source=f"{name}_n{n}_{variant}.aag")
                    if f.n_vars > max_vars:
                        skipped.append(f"{name} n={n} k={k} {variant} ({f.n_vars} vars)")
                        continue
                    if not bug:
                        expected = "unsat"
                    elif k_bad is None:
                        expected = "unknown"
                    else:
                        expected = "sat" if k >= k_bad else "unsat"
                    inst = f"{name}_n{n}_k{k:03d}_{variant}"
                    with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                        fp.write(
                            f"c bmc_circuits_v3/{name} N={n} k={k} variant={variant}: {comment}\n"
                        )
                        fp.write(dqdimacs.dumps(f))
                    manifest.append(
                        {
                            "path": f"{inst}.dqdimacs.gz",
                            "expected": expected,
                            "tags": ["bmc_circuits_v3", name, variant],
                            "params": {"N": n, "k": k, "variant": variant, "k_bad": k_bad},
                        }
                    )
                if do_indinv:
                    assert _encode_indinv is not None
                    try:
                        fi = _encode_indinv(seq, source=f"{name}_n{n}_{variant}.aag")
                    except Exception as e:  # encoder still in flux
                        skipped.append(f"{name} n={n} {variant} indinv ({e})")
                        continue
                    if fi.n_vars > max_vars:
                        skipped.append(f"{name} n={n} {variant} indinv ({fi.n_vars} vars)")
                        continue
                    inst = f"{name}_n{n}_indinv_{variant}"
                    with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                        fp.write(
                            f"c bmc_circuits_v3/{name} N={n} variant={variant} indinv: {comment}\n"
                        )
                        fp.write(dqdimacs.dumps(fi))
                    manifest.append(
                        {
                            "path": f"{inst}.dqdimacs.gz",
                            "expected": "unknown",
                            "tags": ["bmc_circuits_v3", name, variant, "indinv"],
                            "params": {"N": n, "variant": variant, "encoding": "indinv"},
                        }
                    )
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        total += len(manifest)
        print(f"{name}: {len(manifest)} instances → {d}/")

    legacy = {**REGISTRY, **REGISTRY_V2}
    for name, lfn in sorted(legacy.items()):
        d = base / f"legacy_{name}"
        d.mkdir(parents=True, exist_ok=True)
        manifest = []
        for n in ws:
            aag, comment = lfn(n)
            (d / f"{name}_n{n}.aag").write_text(aag)
            seq = parse_seq_aag(aag)
            for k in ks:
                f = encode(seq, k=k, source=f"{name}_n{n}.aag")
                if f.n_vars > max_vars:
                    skipped.append(f"legacy/{name} n={n} k={k} ({f.n_vars} vars)")
                    continue
                inst = f"{name}_n{n}_k{k:03d}"
                with gzip.open(d / f"{inst}.dqdimacs.gz", "wt") as fp:
                    fp.write(f"c bmc_circuits_v3/legacy_{name} N={n} k={k}: {comment}\n")
                    fp.write(dqdimacs.dumps(f))
                manifest.append(
                    {
                        "path": f"{inst}.dqdimacs.gz",
                        "expected": "unknown",
                        "tags": ["bmc_circuits_v3", "legacy", name],
                        "params": {"N": n, "k": k},
                    }
                )
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        total += len(manifest)
        print(f"legacy_{name}: {len(manifest)} instances → {d}/")

    print(f"total: {total} instances; {len(skipped)} skipped (>{max_vars} vars)")
    for s in skipped[:20]:
        print(f"  skip: {s}")
    if len(skipped) > 20:
        print(f"  ... +{len(skipped) - 20} more")


if __name__ == "__main__":
    main()
