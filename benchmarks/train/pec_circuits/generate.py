"""Partial Equivalence Checking instances over the in-repo circuit zoo.

For each *safe* sequential circuit (one whose `bad` is unreachable —
mutex, fifo1, alu_add) at width N and BMC bound K, black-box 1..3
*transition-only* AND-gates and ask
`∃ bb-functions. ∀ inputs. ⋀_{t≤K} ¬bad_t` (encode_unrolled, safe=True).

Two kinds:
  "complete": the original circuit. SAT iff the black-box's
    primary-input cone is rich enough to express a safe completion
    (the Gitina encoding restricts bb deps to *primary inputs only*,
    so a bb whose original function reads a latch may have no safe
    completion → UNSAT is possible here too).
  "mutant": one bad-cone-only gate has an operand negated. The
    black-box (transition-only) cannot rewrite the bad cone, so any
    bug introduced there is irreparable. Usually UNSAT, but a mutation
    that happens to preserve safety stays SAT.

Because neither kind is SAT/UNSAT by construction, `expected` is set
from an hqs probe (`--probe`, the default). Without hqs the manifest
records `expected: "unknown"`.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import tempfile
from pathlib import Path

import click

from core import dqdimacs
from tools.bmc2dqbf.circuits import REGISTRY
from tools.pec2dqbf.aiger_seq import SeqAig, parse_seq_aag
from tools.pec2dqbf.encode import encode_unrolled

# Circuits whose `bad` is provably unreachable for every input trace.
SAFE_CIRCUITS = ("mutex", "fifo1", "alu_add")


def _gate_cone(circ: SeqAig, lit: int) -> set[int]:
    """Gates (even lits) reachable backwards from `lit`."""
    gm = circ.gate_map()
    out: set[int] = set()
    stack = [lit]
    while stack:
        v = stack.pop() & ~1
        if v in out or v not in gm:
            continue
        out.add(v)
        a, b = gm[v]
        stack += [a, b]
    return out


def _classify_gates(circ: SeqAig) -> tuple[list[int], list[int]]:
    """Split gates into (bad_cone_only, transition_only).

    bad_cone_only: gates reachable from `bad` but not from any latch-next.
    transition_only: gates reachable from some latch-next but not from `bad`.
    Gates in both are excluded from either list.
    """
    bad_cone = _gate_cone(circ, circ.bad)
    trans_cone: set[int] = set()
    for lat in circ.latches:
        trans_cone |= _gate_cone(circ, lat.next)
    return (
        [g for g, _, _ in circ.gates if g in bad_cone and g not in trans_cone],
        [g for g, _, _ in circ.gates if g in trans_cone and g not in bad_cone],
    )


def _rank_by_input_cone(circ: SeqAig, gates: list[int]) -> list[int]:
    """Order gates by descending primary-input cone size."""
    src = set(circ.inputs)
    leaves = src | {lat.lit for lat in circ.latches}
    gm = circ.gate_map()

    def csize(g: int) -> int:
        a, b = gm[g]
        return len((circ.cone_inputs(a, leaves) | circ.cone_inputs(b, leaves)) & src)

    return sorted(gates, key=lambda g: (-csize(g), g))


def _mutate(circ: SeqAig, target: int) -> SeqAig:
    """Return a copy with gate `target`'s first operand negated."""
    gates = [(g, a ^ 1, b) if g == target else (g, a, b) for g, a, b in circ.gates]
    return SeqAig(circ.max_var, circ.inputs, circ.latches, circ.outputs, gates, circ.symbols)


def _probe_hqs(f, hqs: Path | None) -> str:
    if not hqs or not hqs.exists():
        return "?"
    with tempfile.NamedTemporaryFile("w", suffix=".dqdimacs", delete=False) as tf:
        tf.write(dqdimacs.dumps(f))
        tmp = tf.name
    try:
        rc = subprocess.run([str(hqs), tmp], capture_output=True, timeout=30).returncode
    except subprocess.TimeoutExpired:
        return "timeout"
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {10: "sat", 20: "unsat"}.get(rc, "?")


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/pec_circuits/instances")
@click.option("-N", "widths", default="4,8,12,16,20,24")
@click.option("-K", "bounds", default="2,4,8")
@click.option("--n-blackboxes", default="1,2,3")
@click.option("--probe/--no-probe", default=True, help="Set expected= from an hqs probe")
def main(out: str, widths: str, bounds: str, n_blackboxes: str, probe: bool) -> None:
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    ws = [int(x) for x in widths.split(",")]
    ks = [int(x) for x in bounds.split(",")]
    nbbs = [int(x) for x in n_blackboxes.split(",")]
    root = Path(__file__).resolve().parents[3]
    hqs_candidates = [
        root / "third_party/hqs/HQS/build/src/hqs/hqs2",
        Path("/root/opensrc/dqbf/third_party/hqs/HQS/build/src/hqs/hqs2"),
    ]
    hqs = next((p for p in hqs_candidates if p.exists()), None)

    manifest = []
    for cname in SAFE_CIRCUITS:
        builder = REGISTRY[cname]
        for n in ws:
            aag, _doc = builder(n)
            (outdir / f"{cname}_n{n}.aag").write_text(aag)
            circ = parse_seq_aag(aag)
            bad_only, trans_only = _classify_gates(circ)
            ranked = _rank_by_input_cone(circ, trans_only)
            for k in ks:
                for nbb in nbbs:
                    if nbb > len(ranked):
                        continue
                    # Black-boxes: transition-only gates with the largest
                    # primary-input cones (bigger bb deps → harder PEC).
                    bb = ranked[:nbb]
                    bb_set = set(bb)

                    cases = [("complete", circ, None)]
                    if bad_only:
                        cases.append(("mutant", _mutate(circ, bad_only[0]), bad_only[0]))
                    for kind, c, tgt in cases:
                        f = encode_unrolled(c, k=k, blackboxes=bb_set, safe=True)
                        stem = f"pec_{cname}_n{n}_k{k}_bb{nbb}_{kind}"
                        probed = _probe_hqs(f, hqs) if probe else ""
                        expected = probed if probed in ("sat", "unsat") else "unknown"
                        _write(outdir, stem, f, cname, n, k, bb, tgt, expected, probed)
                        manifest.append(_entry(stem, expected, cname, n, k, nbb, kind))

    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    by = {"sat": 0, "unsat": 0, "unknown": 0}
    for m in manifest:
        by[m["expected"]] = by.get(m["expected"], 0) + 1
    print(
        f"wrote {len(manifest)} instances "
        f"({by['sat']} sat / {by['unsat']} unsat / {by['unknown']} unknown) to {outdir}/"
    )


def _write(outdir, stem, f, cname, n, k, bb, mut, expected, probed):
    with gzip.open(outdir / f"{stem}.dqdimacs.gz", "wt") as fp:
        fp.write(
            f"c pec_circuits/generate.py circuit={cname} N={n} K={k} "
            f"blackboxes={bb} mutate={mut} expected={expected}"
            + (f" hqs_probed={probed}" if probed else "")
            + "\n"
        )
        fp.write(dqdimacs.dumps(f))


def _entry(stem, expected, cname, n, k, nbb, kind):
    return {
        "path": f"{stem}.dqdimacs.gz",
        "expected": expected,
        "tags": ["pec_circuits", cname, kind],
        "params": {"N": n, "K": k, "n_bb": nbb, "circuit": cname, "kind": kind},
    }


if __name__ == "__main__":
    main()
