"""Render a multi-solver benchmark JSONL to a self-contained HTML report.

Top: interactive explorer (family filter, single-solver inspector,
pairwise comparator) driven by inline vanilla JS over an embedded copy
of the result rows. Bottom: static at-a-glance tables + cactus.
Single file, no external assets, works offline.
"""

from __future__ import annotations

import html as _html
import json
from collections import defaultdict
from pathlib import Path

CSS = (
    "body{font-family:system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em}"
    "table{border-collapse:collapse;margin:.5em 0}"
    "th,td{border:1px solid #ccc;padding:.25em .5em;font-size:.9em}"
    "th{background:#eee}.warn{background:#fdd;font-weight:600}"
    "svg{border:1px solid #ddd;margin:.5em;background:#fff}"
    "h2{border-bottom:1px solid #ccc;padding-bottom:.2em}"
    "h3{margin:.8em 0 .2em}"
    "#controls{position:sticky;top:0;background:#fafafa;border:1px solid #ccc;"
    "padding:.6em;margin:.5em 0 1em;display:flex;flex-wrap:wrap;gap:1.2em;"
    "align-items:center;font-size:.9em;z-index:1}"
    "#controls fieldset{border:1px solid #ddd;padding:.3em .5em}"
    "#controls label{margin-right:.6em}"
    ".panel{border:1px solid #ddd;padding:.6em;margin-bottom:1em}"
    ".scroll{max-height:14em;overflow:auto;border:1px solid #eee;padding:.3em;"
    "font-family:ui-monospace,monospace;font-size:.85em}"
    ".scroll div{white-space:nowrap}"
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
            f'<text x="{w - 100}" y="{20 + i * 16}" fill="{c}" font-size="12">{_esc(s)} ({len(ts)})</text>'
        )
    axes = (
        f'<line x1="40" y1="{h - 30}" x2="{w - 20}" y2="{h - 30}" stroke="#000"/>'
        f'<line x1="40" y1="20" x2="40" y2="{h - 30}" stroke="#000"/>'
        f'<text x="{w // 2}" y="{h - 8}" font-size="11" text-anchor="middle"># solved</text>'
        f'<text x="12" y="{h // 2}" font-size="11" transform="rotate(-90 12 {h // 2})">wall time (s, max={t_max:.2f})</text>'
    )
    return f'<svg width="{w}" height="{h}">{axes}{"".join(paths)}</svg>'


def _js_json(obj: object) -> str:
    # Prevent </script> breakout inside the inline data block.
    return json.dumps(obj).replace("</", "<\\/")


# Only the fields the JS needs — keeps the embedded blob small.
_JS_FIELDS = ("solver", "path", "family", "expected", "got", "wall_s", "cert_status", "cert_bytes")


def _controls_html(solvers: list[str], families: list[str]) -> str:
    fam_boxes = "".join(
        f'<label><input type="checkbox" class="famchk" value="{_esc(f)}" checked> {_esc(f)}</label>'
        for f in families
    )
    opts = "".join(f'<option value="{_esc(s)}">{_esc(s)}</option>' for s in solvers)
    b_default = solvers[1] if len(solvers) > 1 else solvers[0] if solvers else ""
    opts_b = "".join(
        f'<option value="{_esc(s)}"{" selected" if s == b_default else ""}>{_esc(s)}</option>'
        for s in solvers
    )
    return f"""
<div id="controls">
  <fieldset><legend>families</legend>{fam_boxes}</fieldset>
  <fieldset><legend>result</legend>
    <label><input type="radio" name="resf" value="all" checked> all</label>
    <label><input type="radio" name="resf" value="sat"> sat</label>
    <label><input type="radio" name="resf" value="unsat"> unsat</label>
  </fieldset>
  <fieldset><legend>single</legend><select id="solo">{opts}</select></fieldset>
  <fieldset><legend>compare</legend>
    A <select id="cmpA">{opts}</select> vs B <select id="cmpB">{opts_b}</select>
  </fieldset>
</div>
"""


_JS = r"""
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const SOLVED = new Set(["sat","unsat"]);
const SVGNS = "http://www.w3.org/2000/svg";
const lg = t => Math.log10(Math.max(t, 1e-3)) + 3;  // shift so 1e-3 -> 0

function el(tag, attrs, kids){
  const n = document.createElement(tag);
  for (const [k,v] of Object.entries(attrs||{})){
    if (k === "text") n.textContent = v; else n.setAttribute(k, v);
  }
  for (const c of (kids||[])) n.appendChild(c);
  return n;
}
function svg(tag, attrs){
  const n = document.createElementNS(SVGNS, tag);
  for (const [k,v] of Object.entries(attrs||{})) n.setAttribute(k, v);
  return n;
}
function tbl(headers, rows){
  const t = el("table");
  const hr = el("tr");
  for (const h of headers) hr.appendChild(el("th",{text:h}));
  t.appendChild(hr);
  for (const r of rows){
    const tr = el("tr");
    for (const c of r) tr.appendChild(el("td",{text:String(c)}));
    t.appendChild(tr);
  }
  return t;
}

function state(){
  const fams = new Set($$(".famchk").filter(c=>c.checked).map(c=>c.value));
  const resf = ($$("input[name=resf]").find(r=>r.checked)||{}).value || "all";
  return {
    fams, resf,
    solo: $("#solo").value,
    a: $("#cmpA").value, b: $("#cmpB").value,
  };
}
function rowsFor(solver, st){
  return DATA.filter(r =>
    r.solver === solver &&
    st.fams.has(r.family) &&
    (st.resf === "all" || r.expected === st.resf));
}

function renderSingle(){
  const st = state();
  const rs = rowsFor(st.solo, st);
  const root = $("#single"); root.textContent = "";
  root.appendChild(el("h3",{text:`Solver: ${st.solo} — ${rs.length} instances`}));

  // per-family
  const byFam = {};
  for (const r of rs){
    const f = byFam[r.family] ||= {n:0,sat:0,unsat:0,unknown:0,timeout:0,error:0};
    f.n++; f[r.got] = (f[r.got]||0)+1;
  }
  const famRows = Object.keys(byFam).sort().map(f=>{
    const d=byFam[f]; const solved=(d.sat||0)+(d.unsat||0);
    return [f,d.n,solved,d.sat||0,d.unsat||0,d.unknown||0,d.timeout||0,d.error||0];
  });
  root.appendChild(tbl(["family","n","solved","sat","unsat","unknown","timeout","error"], famRows));

  // cert table
  const cert = {sat:{}, unsat:{}};
  for (const r of rs) if (SOLVED.has(r.got)){
    const c = cert[r.got];
    c.n=(c.n||0)+1;
    if (r.cert_status && r.cert_status!=="n/a"){ c.with=(c.with||0)+1; c.bytes=(c.bytes||0)+(r.cert_bytes||0); }
    c[r.cert_status||"n/a"]=(c[r.cert_status||"n/a"]||0)+1;
  }
  const certRows=[];
  for (const res of ["sat","unsat"]){
    const c=cert[res]; if(!c.n) continue;
    const inv=(c.invalid||0)+(c.dep||0)+(c.error||0);
    const skip=(c.skipped||0)+(c.timeout||0);
    certRows.push([res,c.n,c.with||0,c.valid||0,inv,skip,c.with?Math.round((c.bytes||0)/(c.with)):0]);
  }
  root.appendChild(el("h3",{text:"certificates"}));
  root.appendChild(tbl(["result","#","with cert","valid","invalid/dep/err","skipped/timeout","avg bytes"],certRows));

  // histogram (log-spaced)
  const ts = rs.filter(r=>SOLVED.has(r.got)).map(r=>r.wall_s);
  root.appendChild(el("h3",{text:"solve-time histogram (log s)"}));
  root.appendChild(histogram(ts));

  // unsolved
  const un = rs.filter(r=>!SOLVED.has(r.got));
  root.appendChild(el("h3",{text:`unsolved (${un.length})`}));
  const box = el("div",{class:"scroll"});
  for (const r of un) box.appendChild(el("div",{text:`[${r.got}] ${r.path}`}));
  root.appendChild(box);
}

function histogram(ts){
  const W=520,H=180,B=10;
  const span = lg(TIMEOUT*1.1);
  const bins = new Array(B).fill(0);
  for (const t of ts){
    let i = Math.floor(lg(t)/span*B); if(i>=B)i=B-1; if(i<0)i=0; bins[i]++;
  }
  const m = Math.max(1,...bins);
  const s = svg("svg",{width:W,height:H});
  s.appendChild(svg("line",{x1:30,y1:H-20,x2:W-10,y2:H-20,stroke:"#000"}));
  for (let i=0;i<B;i++){
    const bw=(W-40)/B, x=30+i*bw, h=(H-30)*bins[i]/m;
    s.appendChild(svg("rect",{x:x+1,y:H-20-h,width:bw-2,height:h,fill:"#1f77b4"}));
    const lbl=svg("text",{x:x+bw/2,y:H-6,"font-size":9,"text-anchor":"middle"});
    lbl.textContent = (Math.pow(10,(i+1)/B*span-3)).toExponential(0);
    s.appendChild(lbl);
    if(bins[i]){const c=svg("text",{x:x+bw/2,y:H-24-h,"font-size":9,"text-anchor":"middle"});c.textContent=bins[i];s.appendChild(c);}
  }
  return s;
}

function renderPair(){
  const st = state();
  const root = $("#pair"); root.textContent = "";
  const A=st.a, B=st.b;
  root.appendChild(el("h3",{text:`Compare: ${A} vs ${B}`}));
  const ra={}, rb={};
  for (const r of rowsFor(A,st)) ra[r.path]=r;
  for (const r of rowsFor(B,st)) rb[r.path]=r;
  const paths = Object.keys(ra).filter(p=>p in rb);

  // scatter
  root.appendChild(scatter(paths,ra,rb,A,B));

  // head-to-head per family
  const fam={};
  const dis=[];
  for (const p of paths){
    const x=ra[p], y=rb[p];
    const f=fam[x.family] ||= {n:0,aonly:0,bonly:0,both:0,neither:0,dis:0};
    f.n++;
    const sa=SOLVED.has(x.got), sb=SOLVED.has(y.got);
    if(sa&&sb){f.both++; if(x.got!==y.got){f.dis++;dis.push([p,x.got,y.got]);}}
    else if(sa)f.aonly++; else if(sb)f.bonly++; else f.neither++;
  }
  const hrows=Object.keys(fam).sort().map(k=>{
    const d=fam[k];return [k,d.n,d.both,d.aonly,d.bonly,d.neither,d.dis];
  });
  root.appendChild(tbl(["family","n","both",`${A} only`,`${B} only`,"neither","disagree"],hrows));

  root.appendChild(el("h3",{text:`disagreements (${dis.length})`}));
  const box=el("div",{class:"scroll"});
  for(const [p,ga,gb] of dis) box.appendChild(el("div",{text:`${p}  ${A}=${ga}  ${B}=${gb}`}));
  if(!dis.length) box.appendChild(el("div",{text:"none"}));
  root.appendChild(box);
}

function scatter(paths,ra,rb,A,B){
  const W=360,H=360, span=lg(TIMEOUT*1.1);
  const s=svg("svg",{width:W,height:H});
  s.appendChild(svg("line",{x1:30,y1:H-30,x2:W-10,y2:H-30,stroke:"#000"}));
  s.appendChild(svg("line",{x1:30,y1:10,x2:30,y2:H-30,stroke:"#000"}));
  s.appendChild(svg("line",{x1:30,y1:H-30,x2:W-10,y2:10,stroke:"#aaa","stroke-dasharray":3}));
  const xl=svg("text",{x:W/2,y:H-6,"font-size":11,"text-anchor":"middle"});xl.textContent=`${A} (log s)`;s.appendChild(xl);
  const yl=svg("text",{x:10,y:H/2,"font-size":11,transform:`rotate(-90 10 ${H/2})`});yl.textContent=`${B} (log s)`;s.appendChild(yl);
  for(const p of paths){
    const x=ra[p],y=rb[p];
    const tx=SOLVED.has(x.got)?x.wall_s:TIMEOUT*1.1;
    const ty=SOLVED.has(y.got)?y.wall_s:TIMEOUT*1.1;
    const cx=30+lg(tx)/span*(W-40), cy=H-30-lg(ty)/span*(H-40);
    const col = (SOLVED.has(x.got)&&SOLVED.has(y.got)&&x.got!==y.got)?"#d62728":
                (x.got==="sat"||y.got==="sat")?"#2ca02c":"#1f77b4";
    const c=svg("circle",{cx:cx.toFixed(1),cy:cy.toFixed(1),r:2.5,fill:col,opacity:.7});
    const t=svg("title");t.textContent=`${p}\n${A}: ${x.got} ${x.wall_s}s\n${B}: ${y.got} ${y.wall_s}s`;
    c.appendChild(t);s.appendChild(c);
  }
  return s;
}

function rerender(){renderSingle();renderPair();}
document.addEventListener("DOMContentLoaded",()=>{
  for(const n of $$("#controls input, #controls select")) n.addEventListener("change",rerender);
  rerender();
});
"""


def render(rows: list[dict], out: Path, timeout_s: float) -> None:
    solvers = sorted({r["solver"] for r in rows})
    families = sorted({r["family"] for r in rows})
    n_disagree, disagreements = _agree(rows)

    # --- static section (unchanged from before, minus all-pairs scatter) ---
    fam_rows = []
    for fam in families:
        cells: list = [fam]
        n_inst = len({r["path"] for r in rows if r["family"] == fam})
        for s in solvers:
            n_ok = sum(1 for r in rows if r["family"] == fam and r["solver"] == s and _solved(r))
            cells.append(f"{n_ok}/{n_inst} ({100 * n_ok / max(n_inst, 1):.0f}%)")
        fam_rows.append(cells)

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

    cert_rows: list[list] = []
    cert_warn: list[str] = []
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

    warn_html = ""
    if cert_warn:
        warn_html = (
            '<p class="warn">⚠ Solvers with non-verifiable outputs: '
            f"{_esc(', '.join(cert_warn))}</p>"
        )
    if n_disagree:
        warn_html += (
            f'<p class="warn">⚠ {n_disagree} instance(s) with solver DISAGREEMENT — see below.</p>'
        )

    # --- interactive section: embed data + controls + panels + JS ---
    slim = [{k: r.get(k) for k in _JS_FIELDS} for r in rows]
    data_block = (
        "<script>"
        f"const DATA={_js_json(slim)};"
        f"const SOLVERS={_js_json(solvers)};"
        f"const FAMILIES={_js_json(families)};"
        f"const TIMEOUT={timeout_s};"
        "</script>"
    )

    static = f"""
<h2>Static overview</h2>
<h3>% solved per family</h3>
{_table(["family", *solvers], fam_rows)}
<h3>SAT vs UNSAT (by expected)</h3>
{_table(["expected", "n", *solvers], su_rows)}
<h3>Scaling (cactus)</h3>
{_cactus_svg(rows, solvers)}
<h3>Certificate verification</h3>
{_table(["solver", "result", "#", "with cert", "valid", "invalid/dep/err", "skipped/timeout", "avg bytes"], cert_rows)}
<h3>Disagreements</h3>
{_table(["path", *solvers], [[d["path"], *(d.get(s, "-") for s in solvers)] for d in disagreements]) if disagreements else "<p>none</p>"}
"""

    html = f"""<!doctype html><meta charset=utf-8><title>multi-solver report</title>
<style>{CSS}</style>
<h1>Multi-solver benchmark</h1>
{warn_html}
{data_block}
{_controls_html(solvers, families)}
<div id="single" class="panel"></div>
<div id="pair" class="panel"></div>
<script>{_JS}</script>
{static}
"""
    out.write_text(html)
    print(f"wrote {out}")
