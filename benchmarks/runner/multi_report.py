"""Render a multi-solver benchmark JSONL to a self-contained HTML report.

Sections: per-family % solved, SAT-vs-UNSAT split, cactus plot, pairwise
scatter plots, certificate sizes, and certificate-verification status
per solver (flagging any solver that doesn't reach 100% verifiable).
"""

from __future__ import annotations

import html as _html
import json
import math
from collections import defaultdict
from pathlib import Path

CSS = (
    "body{font-family:system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em}"
    "table{border-collapse:collapse;margin:.5em 0}"
    "th,td{border:1px solid #ccc;padding:.25em .5em;font-size:.9em}"
    "th{background:#eee}.warn{background:#fdd;font-weight:600}"
    "svg{border:1px solid #ddd;margin:.5em}"
    "h2{border-bottom:1px solid #ccc;padding-bottom:.2em}"
)


def load(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _solved(r: dict) -> bool:
    return r["got"] in ("sat", "unsat")


def _agree(rows: list[dict]) -> tuple[int, list[dict]]:
    by_inst: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        by_inst[r["path"]][r["solver"]] = r["got"]
    n = 0
    disagreements = []
    for path, results in by_inst.items():
        answers = {v for v in results.values() if v in ("sat", "unsat")}
        if len(answers) > 1:
            n += 1
            disagreements.append({"path": path, **results})
    return n, disagreements


def _esc(x: object) -> str:
    return _html.escape(str(x), quote=True)


def _table(headers: list[str], rows: list[list]) -> str:
    h = "".join(f"<th>{_esc(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{body}</table>"


def _cactus_svg(rows: list[dict], solvers: list[str], w: int = 520, h: int = 320) -> str:
    times: dict[str, list[float]] = {
        s: sorted(r["wall_s"] for r in rows if r["solver"] == s and _solved(r)) for s in solvers
    }
    n_max = max((len(v) for v in times.values()), default=1) or 1
    t_max = max((v[-1] for v in times.values() if v), default=1.0)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
    paths = []
    for i, s in enumerate(solvers):
        ts = times[s]
        if not ts:
            continue
        pts = " ".join(
            f"{40 + (k + 1) / n_max * (w - 60):.1f},{h - 30 - (t / t_max) * (h - 50):.1f}"
            for k, t in enumerate(ts)
        )
        c = colors[i % len(colors)]
        paths.append(
            f'<polyline fill="none" stroke="{c}" stroke-width="2" points="{pts}"/>'
            f'<text x="{w - 100}" y="{20 + i * 16}" fill="{c}" font-size="12">{_esc(s)} ({len(ts)})</text>'  # noqa: E501
        )
    axes = (
        f'<line x1="40" y1="{h - 30}" x2="{w - 20}" y2="{h - 30}" stroke="#000"/>'
        f'<line x1="40" y1="20" x2="40" y2="{h - 30}" stroke="#000"/>'
        f'<text x="{w // 2}" y="{h - 8}" font-size="11" text-anchor="middle"># solved</text>'
        f'<text x="12" y="{h // 2}" font-size="11" transform="rotate(-90 12 {h // 2})">wall time (s, max={t_max:.2f})</text>'
    )
    return f'<svg width="{w}" height="{h}">{axes}{"".join(paths)}</svg>'


def _scatter_svg(
    rows: list[dict], sa: str, sb: str, t_max: float, w: int = 320, h: int = 320
) -> str:
    by_inst: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        by_inst[r["path"]][r["solver"]] = r["wall_s"] if _solved(r) else t_max * 1.1

    def lg(t: float) -> float:
        return math.log10(max(t, 1e-3)) - math.log10(1e-3)

    span = math.log10(t_max * 1.1) - math.log10(1e-3)
    pts = []
    for d in by_inst.values():
        if sa in d and sb in d:
            x = 30 + lg(d[sa]) / span * (w - 40)
            y = h - 30 - lg(d[sb]) / span * (h - 40)
            pts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="#1f77b4" opacity="0.6"/>')
    diag = f'<line x1="30" y1="{h - 30}" x2="{w - 10}" y2="10" stroke="#aaa" stroke-dasharray="3"/>'
    axes = (
        f'<line x1="30" y1="{h - 30}" x2="{w - 10}" y2="{h - 30}" stroke="#000"/>'
        f'<line x1="30" y1="10" x2="30" y2="{h - 30}" stroke="#000"/>'
        f'<text x="{w // 2}" y="{h - 6}" font-size="11" text-anchor="middle">{_esc(sa)} (log s)</text>'
        f'<text x="10" y="{h // 2}" font-size="11" transform="rotate(-90 10 {h // 2})">{_esc(sb)} (log s)</text>'
    )
    return f'<svg width="{w}" height="{h}">{diag}{axes}{"".join(pts)}</svg>'


def render(rows: list[dict], out: Path, timeout_s: float) -> None:
    solvers = sorted({r["solver"] for r in rows})
    families = sorted({r["family"] for r in rows})
    n_disagree, disagreements = _agree(rows)

    # Per-family % solved
    fam_rows = []
    for fam in families:
        cells: list = [fam]
        n_inst = len({r["path"] for r in rows if r["family"] == fam})
        for s in solvers:
            n_ok = sum(1 for r in rows if r["family"] == fam and r["solver"] == s and _solved(r))
            cells.append(f"{n_ok}/{n_inst} ({100 * n_ok / max(n_inst, 1):.0f}%)")
        fam_rows.append(cells)

    # SAT vs UNSAT
    su_rows = []
    for exp in ("sat", "unsat", "unknown"):
        n_inst = len({r["path"] for r in rows if r["expected"] == exp})
        if n_inst == 0:
            continue
        cells = [exp, str(n_inst)]
        for s in solvers:
            n_ok = sum(1 for r in rows if r["expected"] == exp and r["solver"] == s and _solved(r))
            cells.append(f"{n_ok} ({100 * n_ok / n_inst:.0f}%)")
        su_rows.append(cells)

    # Certificate verification status — per (solver, result)
    cert_rows = []
    cert_warn = []
    for s in solvers:
        for res in ("sat", "unsat"):
            srows = [r for r in rows if r["solver"] == s and r["got"] == res]
            n = len(srows)
            if n == 0:
                continue
            with_cert = sum(1 for r in srows if r["cert_path"])
            valid = sum(1 for r in srows if r["cert_status"] == "valid")
            invalid = sum(1 for r in srows if r["cert_status"] in ("invalid", "dep", "error"))
            skipped = sum(1 for r in srows if r["cert_status"] in ("skipped", "timeout"))
            avg_bytes = sum(r["cert_bytes"] for r in srows) // max(with_cert, 1)
            cert_rows.append([s, res, n, with_cert, valid, invalid, skipped, avg_bytes])
            if with_cert > 0 and (with_cert - valid - skipped) > 0:
                cert_warn.append(f"{s}/{res}")

    # Scatter plots: every pair
    scatters = "".join(
        _scatter_svg(rows, solvers[i], solvers[j], timeout_s)
        for i in range(len(solvers))
        for j in range(i + 1, len(solvers))
    )

    warn_html = ""
    if cert_warn:
        warn_html = (
            '<p class="warn">⚠ Solvers with non-verifiable SAT outputs: '
            f"{_esc(', '.join(cert_warn))}</p>"
        )
    if n_disagree:
        warn_html += (
            f'<p class="warn">⚠ {n_disagree} instance(s) with solver DISAGREEMENT — see end.</p>'
        )

    html = f"""<!doctype html><meta charset=utf-8><title>multi-solver report</title>
<style>{CSS}</style>
<h1>Multi-solver benchmark</h1>
{warn_html}
<h2>% solved per family</h2>
{_table(["family", *solvers], fam_rows)}
<h2>SAT vs UNSAT</h2>
{_table(["expected", "n", *solvers], su_rows)}
<h2>Scaling (cactus)</h2>
{_cactus_svg(rows, solvers)}
<h2>Pairwise scatter (log-log; above diagonal = column solver faster)</h2>
{scatters}
<h2>Certificate verification</h2>
{_table(["solver", "result", "#", "with cert", "valid", "invalid/dep/err", "skipped/timeout", "avg bytes"], cert_rows)}
<h2>Disagreements</h2>
{_table(["path", *solvers], [[d["path"], *(d.get(s, "-") for s in solvers)] for d in disagreements]) if disagreements else "<p>none</p>"}
"""
    out.write_text(html)
    print(f"wrote {out}")
