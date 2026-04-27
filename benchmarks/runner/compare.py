"""Compare two benchmark runs (baseline vs candidate)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def load(path: str | Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ln in Path(path).read_text().splitlines():
        if ln.strip():
            r = json.loads(ln)
            out[r["path"]] = r
    return out


def compare(baseline: dict[str, dict], candidate: dict[str, dict]) -> dict:
    fams: dict[str, dict] = defaultdict(
        lambda: {"d_solved": 0, "d_time": 0.0, "regressions": [], "n": 0}
    )
    for path, b in baseline.items():
        c = candidate.get(path)
        if not c:
            continue
        fam = b.get("family", "")
        st = fams[fam]
        st["n"] += 1
        b_ok = b["status"] == "ok"
        c_ok = c["status"] == "ok"
        st["d_solved"] += int(c_ok) - int(b_ok)
        st["d_time"] += c["wall_s"] - b["wall_s"]
        if b_ok and not c_ok:
            st["regressions"].append({"path": path, "was": b["got"], "now": c["got"]})
        if c["status"] == "wrong":
            st["regressions"].append({"path": path, "was": b["got"], "now": "WRONG:" + c["got"]})
    total_d_solved = sum(f["d_solved"] for f in fams.values())
    total_regr = sum(len(f["regressions"]) for f in fams.values())
    return {
        "families": dict(fams),
        "total": {"d_solved": total_d_solved, "regressions": total_regr},
        "accept": total_regr == 0 and total_d_solved >= 0,
    }


def render(cmp: dict) -> str:
    lines = [
        f"accept={cmp['accept']}  Δsolved={cmp['total']['d_solved']:+d}  "
        f"regressions={cmp['total']['regressions']}",
        "",
    ]
    for fam, st in sorted(cmp["families"].items()):
        lines.append(
            f"  {fam}: n={st['n']}  Δsolved={st['d_solved']:+d}  "
            f"Δtime={st['d_time']:+.2f}s  regr={len(st['regressions'])}"
        )
        for r in st["regressions"]:
            lines.append(f"    ! {r['path']}: {r['was']} -> {r['now']}")
    return "\n".join(lines)
