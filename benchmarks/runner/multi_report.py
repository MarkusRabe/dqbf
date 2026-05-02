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
    ".ctl{background:#fafafa;border:1px solid #ccc;padding:.6em;margin:0 0 1em;"
    "display:flex;flex-wrap:wrap;gap:1.2em;align-items:center;font-size:.9em}"
    ".ctl fieldset{border:1px solid #ddd;padding:.3em .5em}"
    ".ctl label{margin-right:.6em}"
    "#tabs{position:sticky;top:0;background:#fff;padding:.4em 0;z-index:1}"
    ".panel{border:1px solid #ddd;padding:.6em;margin-bottom:1em}"
    ".scroll{max-height:14em;overflow:auto;border:1px solid #eee;padding:.3em;"
    "font-family:ui-monospace,monospace;font-size:.85em}"
    ".scroll div{white-space:nowrap}"
    "nav#tabs{margin:.3em 0 0;border-bottom:1px solid #ccc}"
    "nav#tabs button{border:1px solid #ccc;border-bottom:none;background:#f4f4f4;"
    "padding:.4em 1em;margin-right:.3em;cursor:pointer;font-size:.95em}"
    "nav#tabs button.active{background:#fff;font-weight:600;"
    "border-bottom:1px solid #fff;position:relative;top:1px}"
    "section.tab{display:none}section.tab.active{display:block}"
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
    import math

    times: dict[str, list[float]] = {
        s: sorted(r["wall_s"] for r in rows if r["solver"] == s and _solved(r)) for s in solvers
    }
    n_max = max((len(v) for v in times.values()), default=1) or 1
    t_max = max((v[-1] for v in times.values() if v), default=1.0)
    lo, hi = -3, math.ceil(math.log10(max(t_max, 1e-3)))
    span = hi - lo or 1

    def yof(t: float) -> float:
        return h - 30 - (math.log10(max(t, 1e-3)) - lo) / span * (h - 50)

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
    paths = []
    for i, s in enumerate(solvers):
        ts = times[s]
        if not ts:
            continue
        pts = " ".join(
            f"{40 + (k + 1) / n_max * (w - 60):.1f},{yof(t):.1f}" for k, t in enumerate(ts)
        )
        c = colors[i % len(colors)]
        paths.append(
            f'<polyline fill="none" stroke="{c}" stroke-width="2" points="{pts}"/>'
            f'<text x="{w - 100}" y="{20 + i * 16}" fill="{c}" font-size="12">{_esc(s)} ({len(ts)})</text>'
        )
    ticks = []
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        x = 40 + frac * (w - 60)
        ticks.append(
            f'<line x1="{x:.0f}" y1="{h - 30}" x2="{x:.0f}" y2="{h - 26}" stroke="#000"/>'
            f'<text x="{x:.0f}" y="{h - 16}" font-size="9" text-anchor="middle">{int(frac * n_max)}</text>'
        )
    for e in range(lo, hi + 1):
        y = yof(10**e)
        lbl = f"{10**e:g}" if e >= 0 else f"1e{e}"
        ticks.append(
            f'<line x1="36" y1="{y:.0f}" x2="40" y2="{y:.0f}" stroke="#000"/>'
            f'<text x="33" y="{y + 3:.0f}" font-size="9" text-anchor="end">{lbl}</text>'
        )
    axes = (
        f'<line x1="40" y1="{h - 30}" x2="{w - 20}" y2="{h - 30}" stroke="#000"/>'
        f'<line x1="40" y1="20" x2="40" y2="{h - 30}" stroke="#000"/>'
        f'<text x="{w // 2}" y="{h - 4}" font-size="11" text-anchor="middle"># instances solved</text>'
        f'<text x="10" y="{h // 2}" font-size="11" transform="rotate(-90 10 {h // 2})">wall time (s, log)</text>'
        + "".join(ticks)
    )
    return f'<svg width="{w}" height="{h}">{axes}{"".join(paths)}</svg>'


def _js_json(obj: object) -> str:
    # Prevent </script> breakout inside the inline data block.
    return json.dumps(obj).replace("</", "<\\/")


# Only the fields the JS needs — keeps the embedded blob small.
_JS_FIELDS = ("solver", "path", "family", "expected", "got", "wall_s", "cert_status", "cert_bytes")
_CERT_HDR = ["solver", "#", "with cert", "valid", "invalid/dep/err", "skipped/timeout", "avg bytes"]


def _opts(solvers: list[str], selected: str = "") -> str:
    return "".join(
        f'<option value="{_esc(s)}"{" selected" if s == selected else ""}>{_esc(s)}</option>'
        for s in solvers
    )


def _local_controls(scope: str, families: list[str], extra: str) -> str:
    fam = "".join(
        f'<label><input type="checkbox" class="famchk-{scope}" value="{_esc(f)}" checked> '
        f"{_esc(f)}</label>"
        for f in families
    )
    return f"""
<div class="ctl">
  <fieldset><legend>families</legend>{fam}</fieldset>
  <fieldset><legend>result</legend>
    <label><input type="radio" name="resf-{scope}" value="all" checked> all</label>
    <label><input type="radio" name="resf-{scope}" value="sat"> sat</label>
    <label><input type="radio" name="resf-{scope}" value="unsat"> unsat</label>
  </fieldset>
  {extra}
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

function state(scope){
  const fams = new Set($$(".famchk-"+scope).filter(c=>c.checked).map(c=>c.value));
  const resf = ($$("input[name=resf-"+scope+"]").find(r=>r.checked)||{}).value || "all";
  return {fams, resf};
}
function rowsFor(solver, st){
  return DATA.filter(r =>
    r.solver === solver &&
    st.fams.has(r.family) &&
    (st.resf === "all" || r.expected === st.resf));
}

function renderSingle(){
  const st = state("single");
  const solo = $("#solo").value;
  const rs = rowsFor(solo, st);
  const root = $("#single"); root.textContent = "";
  root.appendChild(el("h3",{text:`Solver: ${solo} — ${rs.length} instances`}));

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
  const st = state("pair");
  const root = $("#pair"); root.textContent = "";
  const A=$("#cmpA").value, B=$("#cmpB").value;
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
  const W=420,H=420,M=44, span=lg(TIMEOUT*1.1);
  const px = t => M + lg(t)/span*(W-M-12);
  const py = t => H-M - lg(t)/span*(H-M-12);
  const s=svg("svg",{width:W,height:H});
  // axes
  s.appendChild(svg("line",{x1:M,y1:H-M,x2:W-10,y2:H-M,stroke:"#000"}));
  s.appendChild(svg("line",{x1:M,y1:10,x2:M,y2:H-M,stroke:"#000"}));
  // ticks at each power of 10 plus TO
  const ticks=[];
  for(let e=-3; Math.pow(10,e)<=TIMEOUT; e++) ticks.push([Math.pow(10,e), (e<0?`1e${e}`:String(Math.pow(10,e)))]);
  ticks.push([TIMEOUT*1.1,"TO"]);
  for(const [v,lbl] of ticks){
    const x=px(v), y=py(v);
    s.appendChild(svg("line",{x1:x,y1:H-M,x2:x,y2:H-M+4,stroke:"#000"}));
    const tx=svg("text",{x:x,y:H-M+14,"font-size":9,"text-anchor":"middle"});tx.textContent=lbl;s.appendChild(tx);
    s.appendChild(svg("line",{x1:M-4,y1:y,x2:M,y2:y,stroke:"#000"}));
    const ty=svg("text",{x:M-6,y:y+3,"font-size":9,"text-anchor":"end"});ty.textContent=lbl;s.appendChild(ty);
  }
  // diagonals: y=x, y=10x (B 10x slower), y=x/10 (A 10x slower)
  const diag=(k,main)=>{
    const lo=1e-3, hi=TIMEOUT*1.1;
    const t0=Math.max(lo, lo/k), t1=Math.min(hi, hi/k);
    if(t0>=t1) return;
    s.appendChild(svg("line",{x1:px(t0),y1:py(k*t0),x2:px(t1),y2:py(k*t1),
      stroke:main?"#888":"#ccc","stroke-dasharray":main?"4":"2"}));
    if(!main){
      const tm=Math.sqrt(t0*t1);
      const l=svg("text",{x:px(tm)+4,y:py(k*tm)-4,"font-size":9,fill:"#888"});
      l.textContent="10×";s.appendChild(l);
    }
  };
  diag(1,true); diag(10,false); diag(0.1,false);
  // axis labels
  const xl=svg("text",{x:(M+W-10)/2,y:H-6,"font-size":11,"text-anchor":"middle"});xl.textContent=`${A} (s, log)`;s.appendChild(xl);
  const yl=svg("text",{x:12,y:(10+H-M)/2,"font-size":11,transform:`rotate(-90 12 ${(10+H-M)/2})`});yl.textContent=`${B} (s, log)`;s.appendChild(yl);
  // points
  for(const p of paths){
    const x=ra[p],y=rb[p];
    const sa=SOLVED.has(x.got), sb=SOLVED.has(y.got);
    const tx=sa?x.wall_s:TIMEOUT*1.1, ty=sb?y.wall_s:TIMEOUT*1.1;
    const col = (sa&&sb&&x.got!==y.got)?"#d62728":
                (!sa||!sb)?"#999":
                (x.expected==="sat")?"#2ca02c":"#1f77b4";
    const c=svg("circle",{cx:px(tx).toFixed(1),cy:py(ty).toFixed(1),r:2.5,fill:col,opacity:.75});
    const t=svg("title");t.textContent=`${p}\n${A}: ${x.got} ${x.wall_s}s\n${B}: ${y.got} ${y.wall_s}s`;
    c.appendChild(t);s.appendChild(c);
  }
  // legend
  const L=[["#1f77b4","both solved (unsat)"],["#2ca02c","both solved (sat)"],
           ["#d62728","disagree"],["#999","timeout / one unsolved"]];
  const lx=W-150, ly=14;
  s.appendChild(svg("rect",{x:lx-6,y:ly-10,width:152,height:14*L.length+6,fill:"#fff",stroke:"#ccc"}));
  L.forEach(([c,t],i)=>{
    s.appendChild(svg("circle",{cx:lx,cy:ly+i*14,r:3,fill:c}));
    const l=svg("text",{x:lx+8,y:ly+i*14+3,"font-size":9});l.textContent=t;s.appendChild(l);
  });
  return s;
}

function showTab(id){
  for(const s of $$("section.tab")) s.classList.toggle("active", s.id===id);
  for(const b of $$("#tabs button")) b.classList.toggle("active", b.dataset.tab===id);
}
document.addEventListener("DOMContentLoaded",()=>{
  for(const n of $$("#tab-single .ctl input, #tab-single .ctl select"))
    n.addEventListener("change",renderSingle);
  for(const n of $$("#tab-compare .ctl input, #tab-compare .ctl select"))
    n.addEventListener("change",renderPair);
  for(const b of $$("#tabs button")) b.addEventListener("click",()=>showTab(b.dataset.tab));
  renderSingle(); renderPair();
  showTab("tab-overview");
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

    cert_rows: dict[str, list[list]] = {"sat": [], "unsat": []}
    cert_warn: list[str] = []
    for res in ("sat", "unsat"):
        for s in solvers:
            srows = [r for r in rows if r["solver"] == s and r["got"] == res]
            n = len(srows)
            if n == 0:
                continue
            with_cert = sum(1 for r in srows if r["cert_path"])
            valid = sum(1 for r in srows if r["cert_status"] == "valid")
            invalid = sum(1 for r in srows if r["cert_status"] in ("invalid", "dep", "error"))
            skipped = sum(1 for r in srows if r["cert_status"] in ("skipped", "timeout"))
            avg_bytes = sum(r["cert_bytes"] for r in srows) // max(with_cert, 1)
            cert_rows[res].append([s, n, with_cert, valid, invalid, skipped, avg_bytes])
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

    overview = f"""
<h3>% solved per family</h3>
{_table(["family", *solvers], fam_rows)}
<h3>SAT vs UNSAT (by expected)</h3>
{_table(["expected", "n", *solvers], su_rows)}
<h3>Scaling (cactus)</h3>
{_cactus_svg(rows, solvers)}
<h3>SAT certificate verification</h3>
{_table(_CERT_HDR, cert_rows["sat"])}
<h3>UNSAT certificate verification</h3>
{_table(_CERT_HDR, cert_rows["unsat"])}
<h3>Disagreements</h3>
{_table(["path", *solvers], [[d["path"], *(d.get(s, "-") for s in solvers)] for d in disagreements]) if disagreements else "<p>none</p>"}
"""

    tabs_nav = (
        '<nav id="tabs">'
        '<button data-tab="tab-overview">Overview</button>'
        '<button data-tab="tab-single">Single solver</button>'
        '<button data-tab="tab-compare">Compare</button>'
        "</nav>"
    )

    b_default = solvers[1] if len(solvers) > 1 else (solvers[0] if solvers else "")
    single_ctl = _local_controls(
        "single",
        families,
        f'<fieldset><legend>solver</legend><select id="solo">{_opts(solvers)}</select></fieldset>',
    )
    pair_ctl = _local_controls(
        "pair",
        families,
        "<fieldset><legend>compare</legend>"
        f'A <select id="cmpA">{_opts(solvers)}</select> vs '
        f'B <select id="cmpB">{_opts(solvers, b_default)}</select></fieldset>',
    )

    html = f"""<!doctype html><meta charset=utf-8><title>multi-solver report</title>
<style>{CSS}</style>
<h1>Multi-solver report</h1>
{warn_html}
{data_block}
{tabs_nav}
<section id="tab-overview" class="tab panel">{overview}</section>
<section id="tab-single" class="tab panel">{single_ctl}<div id="single"></div></section>
<section id="tab-compare" class="tab panel">{pair_ctl}<div id="pair"></div></section>
<script>{_JS}</script>
"""
    out.write_text(html)
    print(f"wrote {out}")
