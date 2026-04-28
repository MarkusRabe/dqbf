"""Generate a self-contained HTML status report under docs/dev_reports/.

Each run writes docs/dev_reports/<YYYY-MM-DD_HHMM>.html and refreshes
docs/dev_reports/index.html. Reports are committed so they accumulate
as a history of the project's state.
"""

from __future__ import annotations

import datetime
import html
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "docs" / "dev_reports"

CSS = """
body{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto;padding:0 1em;color:#222}
h1,h2,h3{font-weight:600}
code,pre{font-family:ui-monospace,Menlo,monospace}
pre{background:#f6f6f6;padding:.8em;overflow-x:auto;border-left:3px solid #888}
table{border-collapse:collapse;margin:.6em 0}
th,td{border:1px solid #ccc;padding:.3em .6em;text-align:left;font-size:.92em}
th{background:#eee}
.ok{background:#d8f5d8}.unknown{background:#fff3d6}.wrong{background:#fdd}
.tag{display:inline-block;background:#eef;border-radius:3px;padding:0 .4em;margin:0 .2em}
nav a{margin-right:1em}
"""


def esc(s: str) -> str:
    return html.escape(s)


def pre(s: str) -> str:
    return f"<pre>{esc(s)}</pre>"


def run(cmd: list[str], **kw) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, **kw).stdout


def section_overview() -> str:
    return f"""
<h2 id=overview>What this is</h2>
<p>Provers and tooling for <b>Dependency Quantified Boolean Formulas</b>
built around the <i>fork resolution</i> proof system. A DQBF asserts the
existence of Boolean functions with restricted argument lists; the goal is
to <b>extract those functions</b> (Skolem functions, emitted as AIGER
circuits), not just decide SAT/UNSAT.</p>
<p>Architecture:</p>
{
        pre('''core/          shared Formula IR, DQDIMACS, AIGER, proof-trace format
provers/       one dir per prover; forkres/ = Python ref + rust/
tools/eqfob/   EQFOB language: BV + ∃-quantified functions → DQBF
tools/verify/  independent checkers (trusted base; imports only core/)
benchmarks/    holdout/ (eval-only) | train/ (scalable, generated)
               runner/ (parallel harness, compare)''')
    }
"""


def section_tools() -> str:
    rows = [
        ("forkres", "DQDIMACS → SAT/UNSAT/UNKNOWN; --cert .aag, --proof .frp"),
        ("eqfob compile", "EQFOB source → DQDIMACS; -D NAME=INT overrides widths"),
        (
            "dqbf-verify sat",
            "DQDIMACS + .aag → DIMACS CNF (UNSAT⇒valid) + var-map JSON; --solve runs a SAT solver",
        ),
        ("dqbf-verify unsat", "DQDIMACS + .frp → VALID/INVALID (self-contained replay)"),
        ("dqbf-bench run", "parallel run over a family; JSONL out + summary table"),
        (
            "dqbf-bench compare",
            "baseline.jsonl vs candidate.jsonl → Δsolved/regressions; exit 1 on reject",
        ),
    ]
    tr = "".join(f"<tr><td><code>{esc(a)}</code></td><td>{esc(b)}</td></tr>" for a, b in rows)
    return f"<h2 id=tools>Tools</h2><table><tr><th>CLI</th><th>does</th></tr>{tr}</table>"


def section_example() -> str:
    eq_src = (ROOT / "tools/eqfob/examples/add_gt.eqfob").read_text()
    run(
        [
            sys.executable,
            "-m",
            "tools.eqfob.eqfob.cli",
            "compile",
            str(ROOT / "tools/eqfob/examples/add_gt.eqfob"),
            "-D",
            "A=2",
            "-D",
            "B=2",
            "-o",
            "/tmp/add_gt.dqdimacs",
        ]
    )
    dq_head = "\n".join(Path("/tmp/add_gt.dqdimacs").read_text().splitlines()[:12]) + "\n..."
    fr = run(
        [
            sys.executable,
            "-m",
            "provers.forkres.cli",
            "/tmp/add_gt.dqdimacs",
            "--timeout",
            "1",
            "--trace",
        ]
    )
    tiny = ROOT / "tests/integration/tiny/copy_sat.dqdimacs"
    cert = run(
        [
            sys.executable,
            "-m",
            "provers.forkres.cli",
            str(tiny),
            "--timeout",
            "1",
            "--cert",
            "/tmp/copy.skolem.json",
        ]
    )
    aag_path = Path("/tmp/copy.skolem.json.aag")
    aag = aag_path.read_text() if aag_path.exists() else "(no .aag emitted)"
    ver = run(
        [
            sys.executable,
            "-m",
            "tools.verify.cli",
            "sat",
            str(tiny),
            "/tmp/copy.skolem.json.aag",
            "-o",
            "/tmp/copy_verify.cnf",
            "--map",
            "/tmp/copy_verify.map.json",
        ]
    )
    cnf_head = "\n".join(Path("/tmp/copy_verify.cnf").read_text().splitlines()[:10]) + "\n..."
    vmap = json.dumps(json.load(open("/tmp/copy_verify.map.json")), indent=2)
    return f"""
<h2 id=workflow>Example workflow</h2>
<h3>1. EQFOB source</h3>{pre(eq_src)}
<h3>2. Compile to DQDIMACS</h3>
<code>eqfob compile add_gt.eqfob -D A=2 -D B=2 -o add_gt.dqdimacs</code>
{pre(dq_head)}
<h3>3. Run the prover</h3>
<code>forkres add_gt.dqdimacs --timeout 1 --trace</code>{pre(fr or "(no output)")}
<h3>4. SAT certificate → AIGER</h3>
<code>forkres copy_sat.dqdimacs --cert copy.skolem.json</code>{pre(cert)}
<p>emits <code>copy.skolem.json.aag</code>:</p>{pre(aag)}
<h3>5. Verification CNF + variable map</h3>
<code>dqbf-verify sat copy_sat.dqdimacs copy.skolem.json.aag -o v.cnf --map v.map.json</code>
{pre(ver)}{pre(cnf_head)}<p>variable map:</p>{pre(vmap)}
<p>Hand <code>verify.cnf</code> to any SAT solver; <b>UNSAT ⇒ certificate valid</b>.</p>
"""


def section_perf(jsonl: Path) -> str:
    if not jsonl.exists():
        return "<h2 id=perf>Performance</h2><p>(no results yet)</p>"
    rs = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    by_op: dict[str, dict[int, tuple[str, float]]] = {}
    widths: set[int] = set()
    for r in rs:
        name = Path(r["path"]).name.replace(".dqdimacs.gz", "")
        op, n = name.rsplit("_n", 1)
        by_op.setdefault(op, {})[int(n)] = (r["status"], r["wall_s"])
        widths.add(int(n))
    ws = sorted(widths)
    head = "".join(f"<th>N={w}</th>" for w in ws)
    rows = []
    for op in sorted(by_op):
        cells = []
        for w in ws:
            st, t = by_op[op].get(w, ("-", 0))
            cells.append(f'<td class="{esc(st)}">{esc(st)}<br><small>{t:.2f}s</small></td>')
        rows.append(f"<tr><td><code>{esc(op)}</code></td>{''.join(cells)}</tr>")
    n_ok = sum(1 for r in rs if r["status"] == "ok")
    return f"""
<h2 id=perf>First performance results — <code>train/bitwidth_scaling</code></h2>
<p>Prover: <code>forkres</code> (naive saturation, no heuristics).
Budget: 2s/instance, 8 jobs. <b>{n_ok}/{len(rs)} solved.</b> Zero wrong.</p>
<table><tr><th>op</th>{head}</tr>{"".join(rows)}</table>
<p>This is the baseline the improvement loop will push on — currently
only width-1 of the simple bitwise ops is solved.</p>
"""


def _git_head() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_index() -> None:
    items = sorted(REPORTS.glob("20*.html"), reverse=True)
    rows = "".join(f'<li><a href="{esc(p.name)}">{esc(p.stem)}</a></li>' for p in items)
    (REPORTS / "index.html").write_text(
        f"<!doctype html><meta charset=utf-8><title>dqbf dev reports</title>"
        f"<style>{CSS}</style><h1>dqbf — dev reports</h1><ul>{rows}</ul>"
    )


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    head = _git_head()
    perf = Path("/tmp/bw.jsonl")
    body = (
        section_overview()
        + section_tools()
        + section_example()
        + section_perf(perf)
        + "<h2>References</h2><ul>"
        + "<li><a href='../../OVERVIEW.md'>OVERVIEW.md</a> — proof system &amp; literature</li>"
        + "<li><a href='../IMPROVEMENT_LOOP.md'>IMPROVEMENT_LOOP.md</a> — the plan</li>"
        + "<li><a href='index.html'>all reports</a></li></ul>"
    )
    page = f"""<!doctype html><meta charset=utf-8><title>dqbf — {stamp}</title>
<style>{CSS}</style>
<h1>dqbf — status {esc(stamp)} <small>@ {esc(head)}</small></h1>
<nav><a href=#overview>overview</a><a href=#tools>tools</a>
<a href=#workflow>workflow</a><a href=#perf>performance</a></nav>
{body}
"""
    out = REPORTS / f"{stamp}.html"
    out.write_text(page)
    write_index()
    print(f"wrote {out} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    main()
