"""Render a multi-solver benchmark JSONL to an HTML report.

Three tabs (Overview / Single solver / Compare), each with its own
family + result filter, all driven by vanilla JS.

Two output modes:
- **inline** (`render`): single self-contained file; the result rows
  are embedded as `const DATA=[...]`. Works offline, can be sent as
  one file. ~8 MB for a full train-set run. Use for `results/train.html`.
- **split** (`render_split`): a small HTML shell that fetches
  `data/<name>.manifest.json` listing per-(solver, family) `.json.gz`
  shards and assembles `DATA` in the browser. Shards are
  content-addressed (hash of the gzipped bytes), so re-running a
  bench where only one solver changed deduplicates to that solver's
  shards. Backfilling a new family for an existing report = write its
  shards + append paths to the manifest; the HTML and old shards
  don't change. Needs HTTP (`python3 -m http.server`) — `fetch()` is
  blocked over `file://`. Use for `docs/dev_reports/`.
"""

from __future__ import annotations

import gzip
import hashlib
import html as _html
import json
from collections import defaultdict
from pathlib import Path

from benchmarks.runner.solvers import registry

DOMAIN_ORDER = ["dqbf", "qbf", "hwmc", "syntcomp"]

CSS = (
    ":root{--bd:#e1e4e8;--bg:#fafbfc;--fg:#24292f;--mut:#6a737d;--r:8px}"
    "body{font-family:system-ui,sans-serif;max-width:1100px;margin:2em auto;"
    "padding:0 1em;color:var(--fg);background:#fff}"
    "table{border-collapse:separate;border-spacing:0;margin:.6em 0;"
    "border:1px solid var(--bd);border-radius:var(--r);overflow:hidden}"
    "th,td{border-bottom:1px solid var(--bd);padding:.4em .7em;font-size:.9em}"
    "th{background:var(--bg);font-weight:600}"
    "tr:last-child td{border-bottom:none}"
    ".warn{background:#fde7e7;font-weight:600;padding:.6em .9em;"
    "border-radius:var(--r);border:1px solid #f5c2c7}"
    "svg{border:1px solid var(--bd);border-radius:var(--r);margin:.5em;background:#fff}"
    "h2{border-bottom:1px solid var(--bd);padding-bottom:.3em}"
    "h3{margin:.9em 0 .3em;color:var(--fg)}"
    ".ctl{background:var(--bg);border:1px solid var(--bd);border-radius:var(--r);"
    "padding:.8em;margin:0 0 1em;display:flex;flex-wrap:wrap;gap:1.2em;"
    "align-items:flex-start;font-size:.9em}"
    ".ctl fieldset{border:1px solid var(--bd);border-radius:6px;padding:.4em .6em;"
    "background:#fff}"
    ".ctl legend{padding:0 .3em;color:var(--mut);font-size:.85em}"
    ".ctl label{margin-right:.6em}"
    ".ctl select{border:1px solid var(--bd);border-radius:5px;padding:.2em .4em}"
    "#domain{position:sticky;top:0;background:#fff;padding:.6em 0 .4em;z-index:2;"
    "font-size:.9em}"
    "#domain label{margin-right:.3em;cursor:pointer;padding:.35em .8em;"
    "border:1px solid var(--bd);border-radius:999px;background:var(--bg)}"
    "#domain input{margin-right:.35em}"
    "#domain label:has(input:checked){background:#0969da;color:#fff;border-color:#0969da}"
    "#domain label:has(input:disabled){opacity:.4;cursor:not-allowed}"
    "#domain b{margin-right:.6em}"
    "#tabs{position:sticky;top:2.6em;background:#fff;padding:.4em 0;z-index:1}"
    ".panel{border:1px solid var(--bd);border-radius:var(--r);padding:.9em;"
    "margin-bottom:1em;box-shadow:0 1px 2px rgba(0,0,0,.04)}"
    ".scroll{max-height:14em;overflow:auto;border:1px solid var(--bd);"
    "border-radius:6px;padding:.4em;background:var(--bg);"
    "font-family:ui-monospace,monospace;font-size:.85em}"
    ".scroll div{white-space:nowrap}"
    "nav#tabs{margin:.3em 0 .6em}"
    "nav#tabs button{border:1px solid var(--bd);background:var(--bg);"
    "padding:.45em 1.1em;margin-right:.35em;cursor:pointer;font-size:.95em;"
    "border-radius:var(--r) var(--r) 0 0}"
    "nav#tabs button.active{background:#fff;font-weight:600;"
    "box-shadow:0 -2px 0 #0969da inset}"
    "section.tab{display:none}section.tab.active{display:block}"
    "ul.famtree,ul.famtree ul{list-style:none;margin:0;padding:0}"
    "ul.famtree li{line-height:1.7}"
    ".famtree ul.folded{display:none}"
    ".famrow{display:flex;align-items:center;gap:.3em;"
    "border-bottom:1px solid #f0f1f3;padding:.05em 0}"
    ".famrow:hover{background:#f6f8fa}"
    ".famname{flex:1;min-width:0;white-space:nowrap;overflow:hidden;"
    "text-overflow:ellipsis}"
    ".famstats{display:grid;grid-auto-flow:column;gap:0;"
    "font-family:ui-monospace,monospace;font-size:.8em}"
    ".famstats span{width:7.2em;text-align:right;padding:.1em .4em;"
    "border-left:1px solid #f0f1f3}"
    ".famhead{display:flex;align-items:center;gap:.3em;font-weight:600;"
    "border-bottom:1px solid var(--bd);padding:.3em 0;background:var(--bg);"
    "position:sticky;top:0;z-index:1}"
    ".famhead .famname{padding-left:1.4em}"
    ".famhead .famstats span{border-left:none}"
    ".famfold{display:inline-block;width:1em;text-align:center;cursor:pointer;"
    "font-family:ui-monospace,monospace;user-select:none;color:var(--mut)}"
    ".famfold-none{cursor:default;color:transparent}"
    "a.famonly{font-size:.75em;color:var(--mut);margin-left:.3em;cursor:pointer;"
    "text-decoration:none}a.famonly:hover{text-decoration:underline;color:var(--fg)}"
    ".famtree-panel{border:1px solid var(--bd);border-radius:var(--r);"
    "max-height:28em;overflow:auto;margin:.6em 0;font-size:.9em}"
)


def load(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _esc(x: object) -> str:
    return _html.escape(str(x), quote=True)


def _js_json(obj: object) -> str:
    # Prevent </script> breakout inside the inline data block.
    return json.dumps(obj).replace("</", "<\\/")


# Only the fields the JS needs — keeps the embedded blob small.
_JS_FIELDS = ("solver", "path", "family", "expected", "got", "wall_s", "cert_status", "cert_bytes", "problem_key")


def _opts(solvers: list[str], selected: str = "") -> str:
    return "".join(
        f'<option value="{_esc(s)}"{" selected" if s == selected else ""}>{_esc(s)}</option>'
        for s in solvers
    )


def _family_tree(scope: str, families: list[str]) -> str:
    """Nested <ul class="famtree"> with checkbox + per-solver stats per node.

    Each node carries a `data-path` attribute (the path-prefix for interior
    nodes, the full family for leaves) so the JS can attach aggregated
    solved/total per solver. Leaf checkboxes carry class=famchk-<scope>
    and value=<full family path> so state(scope) keeps working; interior
    checkboxes use class=famint-<scope>.
    """
    root: dict = {"_leaf": None, "ch": {}}
    for fam in sorted(families):
        cur = root
        for seg in fam.split("/"):
            cur = cur["ch"].setdefault(seg, {"_leaf": None, "ch": {}})
        cur["_leaf"] = fam

    def emit(label: str, node: dict, depth: int, path: str) -> str:
        leaf, kids = node["_leaf"], node["ch"]
        if leaf is not None:
            cb = f'<input type="checkbox" class="famchk-{scope}" value="{_esc(leaf)}" checked>'
        else:
            cb = f'<input type="checkbox" class="famint-{scope}" checked>'
        if kids:
            fold = '<span class="famfold">▸</span>'
            sub = '<ul class="folded">' + "".join(
                emit(k, v, depth + 1, f"{path}/{k}") for k, v in sorted(kids.items())
            ) + "</ul>"
        else:
            fold = '<span class="famfold famfold-none">·</span>'
            sub = ""
        pad = f'style="padding-left:{depth * 1.2:.1f}em"'
        return (
            f'<li><div class="famrow" data-path="{_esc(path)}" {pad}>'
            f'{fold}{cb}<span class="famname">{_esc(label)}'
            f' <a class="famonly">only</a></span>'
            f'<span class="famstats"></span></div>{sub}</li>'
        )

    inner = "".join(emit(k, v, 1, k) for k, v in sorted(root["ch"].items()))
    return (
        f'<div class="famtree-panel">'
        f'<div class="famhead"><span class="famname">family</span>'
        f'<span class="famstats" id="famstats-hdr-{scope}"></span></div>'
        f'<ul class="famtree" data-scope="{scope}">'
        f'<li><div class="famrow" data-path=""><span class="famfold">▾</span>'
        f'<input type="checkbox" class="famint-{scope}" checked>'
        f'<span class="famname"><b>all</b> <a class="famonly">only</a></span>'
        f'<span class="famstats"></span></div><ul>{inner}</ul></li></ul></div>'
    )


def _local_controls(scope: str, families: list[str], extra: str) -> str:
    return f"""
<div class="ctl">
  <fieldset><legend>result</legend>
    <label><input type="radio" name="resf-{scope}" value="all" checked> all</label>
    <label><input type="radio" name="resf-{scope}" value="sat"> sat</label>
    <label><input type="radio" name="resf-{scope}" value="unsat"> unsat</label>
  </fieldset>
  <fieldset><legend>count</legend>
    <label><input type="radio" name="count-{scope}" value="encodings" checked> encodings</label>
    <label><input type="radio" name="count-{scope}" value="problems"> problems</label>
  </fieldset>
  {extra}
</div>
{_family_tree(scope, families)}
"""


def _warnings(rows: list[dict], solvers: list[str]) -> str:
    # Solvers with non-verifiable outputs (computed once over all data).
    cert_warn: list[str] = []
    for res in ("sat", "unsat"):
        for s in solvers:
            sr = [r for r in rows if r["solver"] == s and r["got"] == res]
            with_cert = sum(1 for r in sr if (r.get("cert_status") or "n/a") != "n/a")
            valid = sum(1 for r in sr if r.get("cert_status") == "valid")
            skipped = sum(1 for r in sr if r.get("cert_status") in ("skipped", "timeout"))
            if with_cert > 0 and (with_cert - valid - skipped) > 0:
                cert_warn.append(f"{s}/{res}")
    # Disagreement count.
    by_inst: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r["got"] in ("sat", "unsat"):
            by_inst[r["path"]].add(r["got"])
    n_dis = sum(1 for v in by_inst.values() if len(v) > 1)
    out = ""
    if cert_warn:
        out += (
            '<p class="warn">⚠ Solvers with non-verifiable outputs: '
            f"{_esc(', '.join(cert_warn))}</p>"
        )
    if n_dis:
        out += f'<p class="warn">⚠ {n_dis} instance(s) with solver DISAGREEMENT — see Overview tab.</p>'
    return out


_JS = r"""
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const SOLVED = new Set(["sat","unsat"]);
const SVGNS = "http://www.w3.org/2000/svg";
const lg = t => Math.log10(Math.max(t, 1e-3)) + 3;  // shift so 1e-3 -> 0
const COLORS = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2"];
const CERT_HDR = ["solver","#","with cert","valid","invalid/dep/err","skipped/timeout","avg bytes"];

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
function svgt(attrs, text){ const n=svg("text",attrs); n.textContent=text; return n; }
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

function activeDomain(){
  const r = $$("input[name=domain]").find(x=>x.checked);
  return r ? r.value : DOMAIN_NAMES[0];
}
function dFams(){
  return FAMS_FOR[activeDomain()] || new Set();
}
function dSolvers(){
  return SOLVERS_FOR[activeDomain()] || [];
}
function state(scope){
  const fams = new Set($$(".famchk-"+scope).filter(c=>c.checked).map(c=>c.value));
  const resf = ($$("input[name=resf-"+scope+"]").find(r=>r.checked)||{}).value || "all";
  const count = ($$("input[name=count-"+scope+"]").find(r=>r.checked)||{}).value || "encodings";
  return {fams, resf, count};
}
function pkey(r){ return r.problem_key || r.path; }
function rowsAll(st){
  const ds = new Set(dSolvers()), df = dFams();
  return DATA.filter(r =>
    ds.has(r.solver) && df.has(r.family) &&
    st.fams.has(r.family) && (st.resf === "all" || r.expected === st.resf));
}
function rowsFor(solver, st){
  return rowsAll(st).filter(r => r.solver === solver);
}

function pctCell(ok, n){
  if(!n) return "—";
  const pct = Math.round(100*ok/n);
  // Heat: red→yellow→green via HSL.
  const bg = `hsl(${Math.round(pct*1.2)} 65% 92%)`;
  const s = el("span",{}); s.style.background = bg;
  s.textContent = `${ok}/${n} ${String(pct).padStart(3)}%`;
  return s;
}

function updateFamStats(scope){
  const SV = dSolvers(), df = dFams();
  const st = state(scope);
  // Per-leaf-family stats over the *full* domain (ignoring checkbox
  // selection — the tree shows what's available, not what's filtered).
  // In "problems" mode, count distinct problem_keys instead of paths;
  // a problem counts as solved if the solver solved *any* encoding of
  // it anywhere (so abc-pdr's solve via the .aag credits under
  // inductive/ too).
  const byProb = st.count === "problems";
  const leaf = {};                       // family -> Set<unit>
  const solvedKey = {};                  // solver -> Set<pkey> (global)
  for(const s of SV) solvedKey[s] = new Set();
  for(const r of DATA){
    if(!df.has(r.family) || !SV.includes(r.solver)) continue;
    if(st.resf!=="all" && r.expected!==st.resf) continue;
    const u = byProb ? pkey(r) : r.path;
    (leaf[r.family] ||= new Set()).add(u);
    if(SOLVED.has(r.got)) solvedKey[r.solver].add(byProb ? pkey(r) : r.path);
  }
  const hdr = $("#famstats-hdr-"+scope);
  if(hdr){ hdr.textContent=""; for(const s of SV) hdr.appendChild(el("span",{text:s})); }
  const tree = $$("ul.famtree").find(t=>t.dataset.scope===scope);
  if(!tree) return;
  for(const row of tree.querySelectorAll(".famrow")){
    const p = row.dataset.path;
    const denom = new Set();
    for(const [f,d] of Object.entries(leaf)){
      if(p==="" || f===p || f.startsWith(p+"/"))
        for(const u of d) denom.add(u);
    }
    const stats = row.querySelector(".famstats");
    stats.textContent = "";
    for(const s of SV){
      let ok=0; for(const u of denom) if(solvedKey[s].has(u)) ok++;
      const c = pctCell(ok, denom.size);
      stats.appendChild(typeof c==="string" ? el("span",{text:c}) : c);
    }
  }
}

function certRowFor(srows){
  const n = srows.length;
  let withc=0, valid=0, inv=0, skip=0, bytes=0;
  for (const r of srows){
    const cs = r.cert_status || "n/a";
    if (cs !== "n/a"){ withc++; bytes += (r.cert_bytes||0); }
    if (cs === "valid") valid++;
    else if (cs==="invalid"||cs==="dep"||cs==="error") inv++;
    else if (cs==="skipped"||cs==="timeout") skip++;
  }
  return [n, withc, valid, inv, skip, withc?Math.round(bytes/withc):0];
}

function cactus(rs, byProb){
  const W=520,H=320;
  const SV = dSolvers();
  const times = {};
  for (const s of SV){
    const solved = rs.filter(r=>r.solver===s && SOLVED.has(r.got));
    if (byProb){
      // One point per problem_key: best wall_s across its encodings.
      const best = {};
      for(const r of solved){
        const k = pkey(r);
        if(best[k]===undefined || r.wall_s<best[k]) best[k]=r.wall_s;
      }
      times[s] = Object.values(best).sort((a,b)=>a-b);
    } else {
      times[s] = solved.map(r=>r.wall_s).sort((a,b)=>a-b);
    }
  }
  const nMax = Math.max(1, ...Object.values(times).map(v=>v.length));
  const tMax = Math.max(1e-3, ...Object.values(times).map(v=>v.length?v[v.length-1]:1e-3));
  const lo=-3, hi=Math.ceil(Math.log10(tMax)), span=Math.max(1,hi-lo);
  const yof = t => H-30 - (Math.log10(Math.max(t,1e-3))-lo)/span*(H-50);
  const s = svg("svg",{width:W,height:H});
  // axes
  s.appendChild(svg("line",{x1:40,y1:H-30,x2:W-20,y2:H-30,stroke:"#000"}));
  s.appendChild(svg("line",{x1:40,y1:20,x2:40,y2:H-30,stroke:"#000"}));
  s.appendChild(svgt({x:W/2,y:H-4,"font-size":11,"text-anchor":"middle"},"# instances solved"));
  s.appendChild(svgt({x:10,y:H/2,"font-size":11,transform:`rotate(-90 10 ${H/2})`},"wall time (s, log)"));
  // ticks
  for (const frac of [0,.25,.5,.75,1]){
    const x=40+frac*(W-60);
    s.appendChild(svg("line",{x1:x,y1:H-30,x2:x,y2:H-26,stroke:"#000"}));
    s.appendChild(svgt({x:x,y:H-16,"font-size":9,"text-anchor":"middle"},String(Math.round(frac*nMax))));
  }
  for (let e=lo;e<=hi;e++){
    const y=yof(Math.pow(10,e));
    s.appendChild(svg("line",{x1:36,y1:y,x2:40,y2:y,stroke:"#000"}));
    s.appendChild(svgt({x:33,y:y+3,"font-size":9,"text-anchor":"end"}, e<0?`1e${e}`:String(Math.pow(10,e))));
  }
  // series
  SV.forEach((sv,i)=>{
    const ts=times[sv]; if(!ts.length) return;
    const pts=ts.map((t,k)=>`${(40+(k+1)/nMax*(W-60)).toFixed(1)},${yof(t).toFixed(1)}`).join(" ");
    const c=COLORS[i%COLORS.length];
    s.appendChild(svg("polyline",{fill:"none",stroke:c,"stroke-width":2,points:pts}));
    s.appendChild(svgt({x:W-100,y:20+i*16,fill:c,"font-size":12},`${sv} (${ts.length})`));
  });
  return s;
}

function renderOverview(){
  const st = state("overview");
  const rs = rowsAll(st);
  const SV = dSolvers();
  const root = $("#overview"); root.textContent = "";
  updateFamStats("overview");

  // SAT vs UNSAT by expected
  const suRows=[];
  for (const exp of ["sat","unsat","unknown"]){
    const n = new Set(rs.filter(r=>r.expected===exp).map(r=>r.path)).size;
    if(!n) continue;
    const cells=[exp,n];
    for (const s of SV){
      const ok = rs.filter(r=>r.expected===exp && r.solver===s && SOLVED.has(r.got)).length;
      cells.push(`${ok} (${Math.round(100*ok/n)}%)`);
    }
    suRows.push(cells);
  }
  root.appendChild(el("h3",{text:"SAT vs UNSAT (by expected)"}));
  root.appendChild(tbl(["expected","n",...SV], suRows));

  // cactus
  root.appendChild(el("h3",{text:"Scaling (cactus)"}));
  root.appendChild(cactus(rs, st.count==="problems"));

  // cert tables
  for (const res of ["sat","unsat"]){
    const rows=[];
    for (const s of SV){
      const sr = rs.filter(r=>r.solver===s && r.got===res);
      if(!sr.length) continue;
      rows.push([s, ...certRowFor(sr)]);
    }
    root.appendChild(el("h3",{text:`${res.toUpperCase()} certificate verification`}));
    root.appendChild(tbl(CERT_HDR, rows));
  }

  // disagreements
  const inst={};
  for (const r of rs) (inst[r.path] ||= {})[r.solver]=r.got;
  const dis=[];
  for (const [p,d] of Object.entries(inst)){
    const ans=new Set(Object.values(d).filter(v=>SOLVED.has(v)));
    if(ans.size>1) dis.push([p, ...SV.map(s=>d[s]||"-")]);
  }
  root.appendChild(el("h3",{text:`Disagreements (${dis.length})`}));
  root.appendChild(dis.length ? tbl(["path",...SV], dis) : el("p",{text:"none"}));
}

function renderSingle(){
  const st = state("single");
  const solo = $("#solo").value;
  const rs = rowsFor(solo, st);
  const root = $("#single"); root.textContent = "";
  updateFamStats("single");
  root.appendChild(el("h3",{text:`Solver: ${solo} — ${rs.length} instances`}));

  // cert table
  const certRows=[];
  for (const res of ["sat","unsat"]){
    const sr = rs.filter(r=>r.got===res);
    if(!sr.length) continue;
    certRows.push([res, ...certRowFor(sr)]);
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
    s.appendChild(svgt({x:x+bw/2,y:H-6,"font-size":9,"text-anchor":"middle"},
      Math.pow(10,(i+1)/B*span-3).toExponential(0)));
    if(bins[i]) s.appendChild(svgt({x:x+bw/2,y:H-24-h,"font-size":9,"text-anchor":"middle"},String(bins[i])));
  }
  return s;
}

function renderPair(){
  const st = state("pair");
  const root = $("#pair"); root.textContent = "";
  updateFamStats("pair");
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
    s.appendChild(svgt({x:x,y:H-M+14,"font-size":9,"text-anchor":"middle"},lbl));
    s.appendChild(svg("line",{x1:M-4,y1:y,x2:M,y2:y,stroke:"#000"}));
    s.appendChild(svgt({x:M-6,y:y+3,"font-size":9,"text-anchor":"end"},lbl));
  }
  // diagonals: y=x, y=10x, y=x/10
  const diag=(k,main)=>{
    const lo=1e-3, hi=TIMEOUT*1.1;
    const t0=Math.max(lo, lo/k), t1=Math.min(hi, hi/k);
    if(t0>=t1) return;
    s.appendChild(svg("line",{x1:px(t0),y1:py(k*t0),x2:px(t1),y2:py(k*t1),
      stroke:main?"#888":"#ccc","stroke-dasharray":main?"4":"2"}));
    if(!main){
      const tm=Math.sqrt(t0*t1);
      s.appendChild(svgt({x:px(tm)+4,y:py(k*tm)-4,"font-size":9,fill:"#888"},"10×"));
    }
  };
  diag(1,true); diag(10,false); diag(0.1,false);
  // axis labels
  s.appendChild(svgt({x:(M+W-10)/2,y:H-6,"font-size":11,"text-anchor":"middle"},`${A} (s, log)`));
  s.appendChild(svgt({x:12,y:(10+H-M)/2,"font-size":11,transform:`rotate(-90 12 ${(10+H-M)/2})`},`${B} (s, log)`));
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
    s.appendChild(svgt({x:lx+8,y:ly+i*14+3,"font-size":9},t));
  });
  return s;
}

function showTab(id){
  for(const s of $$("section.tab")) s.classList.toggle("active", s.id===id);
  for(const b of $$("#tabs button")) b.classList.toggle("active", b.dataset.tab===id);
}

function wireFamTree(tree, render){
  const scope = tree.dataset.scope;
  const leavesOf = li => Array.from(li.querySelectorAll(".famchk-"+scope));
  const interiorsOf = li => Array.from(li.querySelectorAll(".famint-"+scope));
  function syncInterior(){
    const ints = Array.from(tree.querySelectorAll(".famint-"+scope)).reverse();
    for(const cb of ints){
      const ls = leavesOf(cb.closest("li"));
      const on = ls.filter(l=>l.checked).length;
      cb.checked = on===ls.length && ls.length>0;
      cb.indeterminate = on>0 && on<ls.length;
    }
  }
  for(const cb of tree.querySelectorAll(".famint-"+scope)){
    cb.addEventListener("change", ()=>{
      const li = cb.closest("li");
      for(const l of leavesOf(li)) l.checked = cb.checked;
      for(const i of interiorsOf(li)) { i.checked = cb.checked; i.indeterminate=false; }
      syncInterior(); render();
    });
  }
  for(const cb of tree.querySelectorAll(".famchk-"+scope)){
    cb.addEventListener("change", ()=>{ syncInterior(); render(); });
  }
  function setFold(li, folded){
    const ul = li.querySelector(":scope > ul");
    const tg = li.querySelector(":scope > .famrow > .famfold");
    if(!ul || !tg || tg.classList.contains("famfold-none")) return;
    ul.classList.toggle("folded", folded);
    tg.textContent = folded ? "▸" : "▾";
  }
  for(const tg of tree.querySelectorAll(".famfold")){
    if(tg.classList.contains("famfold-none")) continue;
    tg.addEventListener("click", ()=>{
      const li = tg.closest("li");
      const ul = li.querySelector(":scope > ul");
      setFold(li, !ul.classList.contains("folded"));
    });
  }
  for(const a of tree.querySelectorAll("a.famonly")){
    a.addEventListener("click", ev=>{
      ev.preventDefault();
      const li = a.closest("li");
      for(const l of tree.querySelectorAll(".famchk-"+scope)) l.checked=false;
      for(const l of leavesOf(li)) l.checked=true;
      setFold(li, false);
      syncInterior(); render();
    });
  }
  syncInterior();
}

// "ran" = solver attempted the format (not n/a / not error).
const RAN = new Set(["sat","unsat","unknown","timeout"]);
// Which problem domains can a solver of native-domain X handle? DQBF
// solvers cover everything (via encodings); QBF/HWMC/SYNTCOMP tools
// only their own.
const HANDLES = {
  dqbf:     new Set(["dqbf","qbf","hwmc","syntcomp"]),
  qbf:      new Set(["qbf"]),
  hwmc:     new Set(["hwmc"]),
  syntcomp: new Set(["syntcomp"]),
};
// Computed in appInit(), not at module scope: in split-data reports
// `DATA` is empty until the manifest+shards finish loading. Module-scope
// reads of `DATA` would silently bake in an empty result.
const FAMS_FOR = {}, SOLVERS_FOR = {};
function computeDomainSets(){
  for(const d of DOMAIN_NAMES){
    const native = new Set(SOLVERS.filter(s=>DOMAINS[s]===d));
    const fams = new Set(
      DATA.filter(r=>native.has(r.solver) && RAN.has(r.got)).map(r=>r.family));
    FAMS_FOR[d] = fams;
    SOLVERS_FOR[d] = SOLVERS.filter(s=>
      (HANDLES[DOMAINS[s]]||new Set()).has(d) &&
      DATA.some(r=>r.solver===s && fams.has(r.family) && RAN.has(r.got)));
  }
}

function applyDomain(){
  const ds = new Set(dSolvers()), df = dFams();
  // Restrict solver <select>s.
  for(const sel of ["#solo","#cmpA","#cmpB"]){
    const node=$(sel); if(!node) continue;
    for(const o of node.options) o.hidden = !ds.has(o.value);
    if(!ds.has(node.value)){
      const first = [...node.options].find(o=>!o.hidden);
      if(first) node.value = first.value;
    }
  }
  // Restrict family trees: hide leaves outside df and interiors with no visible leaf.
  for(const tree of $$("ul.famtree")){
    const scope = tree.dataset.scope;
    for(const cb of tree.querySelectorAll(".famchk-"+scope))
      cb.closest("li").style.display = df.has(cb.value) ? "" : "none";
    for(const li of [...tree.querySelectorAll("li")].reverse()){
      if(li.querySelector(":scope > .famrow > input.famchk-"+scope)) continue;
      const vis = [...li.querySelectorAll(".famchk-"+scope)]
        .some(l=>l.closest("li").style.display!=="none");
      li.style.display = vis ? "" : "none";
    }
  }
  renderOverview(); renderSingle(); renderPair();
}

function appInit(){
  computeDomainSets();
  const SCOPES = [
    ["overview","tab-overview",renderOverview],
    ["single","tab-single",renderSingle],
    ["pair","tab-compare",renderPair],
  ];
  const renderOf = Object.fromEntries(SCOPES.map(([s,,r])=>[s,r]));
  for(const tree of $$("ul.famtree"))
    wireFamTree(tree, renderOf[tree.dataset.scope]);
  // result-filter radios + solver selects (non-famtree controls)
  for(const [,tab,render] of SCOPES){
    for(const n of $$(`#${tab} .ctl input[type=radio], #${tab} .ctl select`))
      n.addEventListener("change", render);
  }
  for(const b of $$("#tabs button")) b.addEventListener("click",()=>showTab(b.dataset.tab));
  for(const r of $$("#domain input[name=domain]")) r.addEventListener("change", applyDomain);
  applyDomain();
  showTab("tab-overview");
}
"""

# Inline mode: DATA is already defined; run appInit on DOM-ready.
_JS_BOOT_INLINE = (
    '<script>document.addEventListener("DOMContentLoaded",appInit);</script>'
)

# Consolidated mode: one HTML, one manifest grouping shards by solver
# version. Loads only the default-selected solvers' shards on first
# render; toggling a solver version on lazily fetches its shards.
_JS_BOOT_CONSOLIDATED = """\
<script>
async function _gunzipJson(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(`${url}: ${r.status}`);
  const ds = new DecompressionStream("gzip");
  const blob = await new Response(r.body.pipeThrough(ds)).blob();
  return JSON.parse(await blob.text());
}
let _loadedSolvers = new Set();
let _dataBase = null;
let _manifest = null;
async function _loadSolvers(names, status){
  const want = names.filter(s => !_loadedSolvers.has(s) && _manifest.solvers[s]);
  if(!want.length) return;
  const files = want.flatMap(s => _manifest.solvers[s]);
  let n = 0;
  const parts = await Promise.all(files.map(async f => {
    const r = await _gunzipJson(_dataBase + f);
    if(status) status.textContent = `Loading ${++n}/${files.length}…`;
    return r;
  }));
  DATA = DATA.concat(parts.flat());
  for(const s of want) _loadedSolvers.add(s);
}
(async()=>{
  const status = document.createElement("div");
  status.style.cssText = "position:fixed;top:.5em;right:.5em;background:#fff;border:1px solid #ccc;border-radius:6px;padding:.4em .8em;font-size:.85em;color:#666;z-index:99";
  status.textContent = "Loading…";
  document.body.appendChild(status);
  let lastErr=null;
  for(const b of DATA_BASES){
    try{
      const r = await fetch(b + MANIFEST_NAME);
      if(!r.ok){ lastErr = `${b}${MANIFEST_NAME}: ${r.status}`; continue; }
      _manifest = await r.json(); _dataBase = b; break;
    }catch(e){ lastErr = e; }
  }
  if(!_manifest){
    status.remove();
    const d = document.createElement("div");
    d.className = "warn";
    d.append("Failed to load report data (" + lastErr + "). ");
    const c = document.createElement("code");
    c.textContent = "python3 -m http.server";
    d.append("Serve over HTTP — e.g. ", c, " in docs/dev_reports/ — or wait for the GitHub CDN cache.");
    document.body.prepend(d);
    return;
  }
  try{
    const want = $$("#sv-panel input:checked").map(c => c.value);
    await _loadSolvers(want, status);
    status.remove();
    if(document.readyState === "loading")
      document.addEventListener("DOMContentLoaded", appInit);
    else appInit();
    // wire the solver-version panel for lazy loading + re-render
    for(const cb of $$("#sv-panel input")){
      cb.addEventListener("change", async()=>{
        if(cb.checked && !_loadedSolvers.has(cb.value)){
          const s2 = document.createElement("div");
          s2.style.cssText = status.style.cssText; s2.textContent = "Loading…";
          document.body.appendChild(s2);
          await _loadSolvers([cb.value], s2);
          s2.remove();
        }
        SOLVERS = $$("#sv-panel input:checked").map(c => c.value).sort();
        computeDomainSets(); applyDomain();
        for(const tree of $$("ul.famtree")) updateFamStats(tree.dataset.scope);
        renderOverview(); renderSingle(); renderPair();
      });
    }
  }catch(e){
    status.remove();
    const d = document.createElement("div");
    d.className = "warn"; d.textContent = "Failed to load report shards: " + e;
    document.body.prepend(d);
  }
})();
</script>
"""

# Split mode: DATA is empty until the manifest's shards are fetched and
# decompressed. Tries a list of base URLs — relative path for local
# `python3 -m http.server`, then absolute GitHub raw / CDN for proxied
# viewers (htmlpreview.github.io renders the page on its own origin, so
# relative paths 404). All candidates have CORS `*` and serve `.gz`
# without auto-decompression (verified 2026-05-10).
_JS_BOOT_SPLIT = """\
<script>
async function _gunzipJson(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(`${url}: ${r.status}`);
  const ds = new DecompressionStream("gzip");
  const blob = await new Response(r.body.pipeThrough(ds)).blob();
  return JSON.parse(await blob.text());
}
(async()=>{
  const status = document.createElement("div");
  status.style.cssText = "position:fixed;top:.5em;right:.5em;background:#fff;border:1px solid #ccc;border-radius:6px;padding:.4em .8em;font-size:.85em;color:#666;z-index:99";
  status.textContent = "Loading data…";
  document.body.appendChild(status);
  let mf=null, base=null, lastErr=null;
  for(const b of DATA_BASES){
    try{
      const r = await fetch(b + MANIFEST_NAME);
      if(!r.ok){ lastErr = `${b}${MANIFEST_NAME}: ${r.status}`; continue; }
      mf = await r.json(); base = b; break;
    }catch(e){ lastErr = e; }
  }
  if(!mf){
    status.remove();
    const d = document.createElement("div");
    d.className = "warn";
    d.append("Failed to load report data (" + lastErr + "). ");
    const c = document.createElement("code");
    c.textContent = "python3 -m http.server";
    d.append("Serve over HTTP — e.g. ", c, " in docs/dev_reports/ — or wait for the GitHub CDN cache.");
    document.body.prepend(d);
    return;
  }
  try{
    let n = 0;
    const parts = await Promise.all(mf.files.map(async f => {
      const r = await _gunzipJson(base + f);
      status.textContent = `Loading data… ${++n}/${mf.files.length}`;
      return r;
    }));
    DATA = parts.flat();
    status.remove();
    if(document.readyState === "loading")
      document.addEventListener("DOMContentLoaded", appInit);
    else appInit();
  }catch(e){
    status.remove();
    const d = document.createElement("div");
    d.className = "warn"; d.textContent = "Failed to load report shards: " + e;
    document.body.prepend(d);
  }
})();
</script>
"""

# Base URLs the JS tries in order to find `data/<manifest>` and the
# shards it lists. First match wins (a base "matches" if its manifest
# fetch returns 200 with parseable JSON). Order: local-relative first
# (works offline / `python3 -m http.server`), then absolute CDN URLs
# (works via htmlpreview.github.io, file:// with internet, etc.).
_DATA_BASES = [
    "data/",
    "https://raw.githubusercontent.com/MarkusRabe/dqbf/main/docs/dev_reports/data/",
    "https://cdn.jsdelivr.net/gh/MarkusRabe/dqbf@main/docs/dev_reports/data/",
]


def _domain_selector(domains: dict[str, str]) -> str:
    counts = {d: sum(1 for v in domains.values() if v == d) for d in DOMAIN_ORDER}
    default = next((d for d in DOMAIN_ORDER if counts.get(d)), DOMAIN_ORDER[0])
    pills = []
    for d in DOMAIN_ORDER:
        n = counts.get(d, 0)
        dis = "" if n else " disabled"
        chk = " checked" if d == default else ""
        pills.append(
            f'<label><input type="radio" name="domain" value="{_esc(d)}"{dis}{chk}> '
            f"{_esc(d.upper())}{f' ({n})' if n else ''}</label>"
        )
    return f'<div id="domain"><b>Domain:</b>{"".join(pills)}</div>'


def _shell(
    rows: list[dict],
    timeout_s: float,
    data_block: str,
    boot: str,
    *,
    families_override: list[str] | None = None,
    solvers_override: list[str] | None = None,
    domains_override: dict[str, str] | None = None,
    default_solvers: list[str] | None = None,
    solver_panel: str = "",
) -> str:
    """The HTML around `data_block`. `data_block` defines (or arranges
    to define) `DATA`; everything else is static and rendered here.

    The `*_override` args let `render_consolidated` pass the *full*
    solver/family/domain lists from the manifest (not just `rows`),
    so the controls cover lazily-loadable solvers. `default_solvers`
    is the set initially loaded/checked; if omitted, all solvers."""
    solvers = solvers_override or sorted({r["solver"] for r in rows})
    default_on = default_solvers if default_solvers is not None else solvers
    families = families_override or sorted({r["family"] for r in rows})
    if domains_override is None:
        reg = registry()
        domains = {s: (reg[s].domain if s in reg else "dqbf") for s in solvers}
    else:
        domains = domains_override

    # SOLVERS is `let` so the consolidated mode's solver-version panel
    # can reassign it. Initialised to the default-on set; the panel
    # adds/removes versions and re-renders.
    meta_block = (
        "<script>"
        f"let SOLVERS={_js_json(default_on)};"
        f"const FAMILIES={_js_json(families)};"
        f"const DOMAINS={_js_json(domains)};"
        f"const DOMAIN_NAMES={_js_json(DOMAIN_ORDER)};"
        f"const TIMEOUT={timeout_s};"
        "</script>"
    )

    tabs_nav = (
        '<nav id="tabs">'
        '<button data-tab="tab-overview">Overview</button>'
        '<button data-tab="tab-single">Single solver</button>'
        '<button data-tab="tab-compare">Compare</button>'
        "</nav>"
    )
    overview_ctl = _local_controls("overview", families, solver_panel)
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

    import datetime
    import subprocess

    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    # Explicit <head> so htmlpreview.github.io's `<base href>` injection
    # works (its regex matches `<head[^>]*>`). With <base> set, the
    # relative `data/` path resolves against the raw GitHub URL.
    return f"""<!doctype html><html><head><meta charset=utf-8><title>multi-solver report</title>
<style>{CSS}</style></head><body>
<h1>Multi-solver report <small style="color:#888;font-size:.55em">@ {_esc(head)} · {_esc(stamp)}</small></h1>
{_warnings(rows, solvers)}
{data_block}
{meta_block}
{_domain_selector(domains)}
{tabs_nav}
<section id="tab-overview" class="tab panel">{overview_ctl}<div id="overview"></div></section>
<section id="tab-single" class="tab panel">{single_ctl}<div id="single"></div></section>
<section id="tab-compare" class="tab panel">{pair_ctl}<div id="pair"></div></section>
<script>{_JS}</script>
{boot}
</body></html>
"""


def render(rows: list[dict], out: Path, timeout_s: float) -> None:
    """Self-contained inline report (one file, works over file://)."""
    slim = [{k: r.get(k) for k in _JS_FIELDS} for r in rows]
    data_block = f"<script>const DATA={_js_json(slim)};</script>"
    out.write_text(_shell(rows, timeout_s, data_block, _JS_BOOT_INLINE))
    print(f"wrote {out}")


def _slug(s: str) -> str:
    return s.replace("/", "~").replace(" ", "_")


def _write_shards(rows: list[dict], data_dir: Path) -> list[str]:
    """Write per-(solver, family) gzipped JSON shards under `data_dir`.
    Filenames are `<solver>--<family-slug>--<hash[:12]>.json.gz` where
    the hash is over the gzipped bytes — content-addressed, so two
    reports with identical results for a solver share the shard. Idempotent:
    skips files that already exist. Returns the basenames written/found."""
    data_dir.mkdir(parents=True, exist_ok=True)
    by_sf: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by_sf[(r["solver"], r["family"])].append({k: r.get(k) for k in _JS_FIELDS})
    files: list[str] = []
    for (sv, fam), shard_rows in sorted(by_sf.items()):
        # Sort for determinism (same content → same hash regardless of run order).
        shard_rows.sort(key=lambda r: r["path"])
        gz = gzip.compress(json.dumps(shard_rows, separators=(",", ":")).encode(), mtime=0)
        h = hashlib.sha256(gz).hexdigest()[:12]
        name = f"{_slug(sv)}--{_slug(fam)}--{h}.json.gz"
        p = data_dir / name
        if not p.exists():
            p.write_bytes(gz)
        files.append(name)
    return files


def _split_versioned(name: str) -> tuple[str, tuple[int, ...]] | None:
    """`frust-v2.95` -> ('frust', (2, 95)). None if not versioned."""
    import re

    m = re.match(r"^(.+)-v(\d+(?:\.\d+)*)$", name)
    if not m:
        return None
    return m.group(1), tuple(int(x) for x in m.group(2).split("."))


def _default_solvers(solvers: list[str], exclude: tuple[str, ...] = ("forkres",)) -> list[str]:
    """Most-recent version of each base solver; exclude `forkres` by
    default (slow Python reference, not interesting in the headline)."""
    by_base: dict[str, list[tuple[tuple[int, ...], str]]] = defaultdict(list)
    plain: list[str] = []
    for s in solvers:
        if s in exclude:
            continue
        v = _split_versioned(s)
        if v:
            by_base[v[0]].append((v[1], s))
        else:
            plain.append(s)
    latest = [max(vs)[1] for vs in by_base.values()]
    return sorted(plain + latest)


def _solver_panel(solvers: list[str], default_on: set[str]) -> str:
    """Checkbox list grouped by base solver. Versioned solvers are
    sorted newest-first; only the latest is checked by default."""
    groups: dict[str, list[str]] = defaultdict(list)
    plain: list[str] = []
    for s in sorted(solvers):
        v = _split_versioned(s)
        if v:
            groups[v[0]].append(s)
        else:
            plain.append(s)
    items: list[str] = []
    for s in plain:
        chk = " checked" if s in default_on else ""
        items.append(f'<label><input type="checkbox" value="{_esc(s)}"{chk}> {_esc(s)}</label>')
    for _, vers in sorted(groups.items()):
        # Newest first so the default-checked one is at the top.
        vers.sort(key=lambda s: _split_versioned(s)[1], reverse=True)  # type: ignore[index]
        for s in vers:
            chk = " checked" if s in default_on else ""
            items.append(f'<label><input type="checkbox" value="{_esc(s)}"{chk}> {_esc(s)}</label>')
    return (
        '<details id="sv-panel"><summary>solver versions '
        f"({len(default_on)}/{len(solvers)} on)</summary>"
        f'<div style="display:flex;flex-wrap:wrap;gap:.3em 1.2em;padding:.4em 0">'
        f"{''.join(items)}</div></details>"
    )


def render_split(rows: list[dict], out: Path, timeout_s: float) -> None:
    """Shell HTML + content-addressed shards in `<out.parent>/data/`.
    Backfill a new family later: append rows to that family's jsonl,
    call `render_split` again with the *combined* rows, and only the new
    family's shards (plus the manifest and HTML) change on disk."""
    data_dir = out.parent / "data"
    before = {p.name for p in data_dir.glob("*.json.gz")} if data_dir.exists() else set()
    files = _write_shards(rows, data_dir)
    manifest_name = f"{out.stem}.manifest.json"
    (data_dir / manifest_name).write_text(json.dumps({"files": files}, indent=1))
    data_block = (
        "<script>let DATA=[];"
        f"const MANIFEST_NAME={_js_json(manifest_name)};"
        f"const DATA_BASES={_js_json(_DATA_BASES)};</script>"
    )
    out.write_text(_shell(rows, timeout_s, data_block, _JS_BOOT_SPLIT))
    n_new = sum(1 for f in files if f not in before)
    print(f"wrote {out} ({len(files)} shards, {n_new} new)")


CONSOLIDATED_NAME = "report.html"
CONSOLIDATED_MANIFEST = "report.manifest.json"


def render_consolidated(
    rows: list[dict],
    out_dir: Path,
    timeout_s: float,
    *,
    report_name: str = CONSOLIDATED_NAME,
    manifest_name: str = CONSOLIDATED_MANIFEST,
) -> None:
    """Update a consolidated report at `<out_dir>/<report_name>`.

    The manifest at `<out_dir>/data/<manifest_name>` accumulates shard
    lists per solver across runs: a solver in the current `rows` has
    its shard list **replaced**; solvers not in `rows` keep their old
    entries. The HTML's solver-version filter defaults to the most
    recent version of each base solver and excludes `forkres`. Other
    versions are listed but unchecked; toggling one on lazily fetches
    its shards.

    `report_name`/`manifest_name` default to the train-set report; pass
    e.g. `"test_report.html"` / `"test_report.manifest.json"` for
    a separate report over `benchmarks/test/`. The shards (`data/*.json.gz`)
    are content-addressed and shared across reports — the same solver
    on the same instance produces the same shard regardless of which
    report references it.
    """
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / report_name
    mf_path = data_dir / manifest_name

    # Group this run's shards by solver.
    by_solver: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_solver[r["solver"]].append(r)
    new_shards: dict[str, list[str]] = {}
    before = {p.name for p in data_dir.glob("*.json.gz")}
    for sv, sv_rows in by_solver.items():
        new_shards[sv] = _write_shards(sv_rows, data_dir)

    # Merge into the persistent manifest: this run's solvers replace
    # their entries; absent solvers keep their old shard lists.
    mf: dict = {"solvers": {}, "families": [], "domains": {}, "timeout": timeout_s}
    if mf_path.exists():
        try:
            mf = json.loads(mf_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    mf.setdefault("solvers", {}).update(new_shards)
    # Families/domains: union across all known shards (read filenames; a
    # shard's family is encoded in its name `<solver>--<family-slug>--<hash>`).
    fams_from_shards: set[str] = set()
    for shard_list in mf["solvers"].values():
        for f in shard_list:
            parts = f.rsplit("--", 2)
            if len(parts) == 3:
                fams_from_shards.add(parts[1].replace("~", "/"))
    mf["families"] = sorted(fams_from_shards | {r["family"] for r in rows})
    reg = registry()
    mf["domains"] = {
        s: (reg[s].domain if s in reg else "dqbf") for s in sorted(mf["solvers"])
    }
    mf["timeout"] = timeout_s
    mf_path.write_text(json.dumps(mf, indent=1))

    all_solvers = sorted(mf["solvers"])
    defaults = set(_default_solvers(all_solvers))
    families = mf["families"]
    domains = mf["domains"]

    # `rows` may be a partial backfill (e.g. just abc-bmc/abc-pdr). The
    # `_warnings` div is best-effort over what's in `rows`; the rest of
    # the controls use the full manifest lists + `defaults`.
    data_block = (
        "<script>let DATA=[];"
        f"const MANIFEST_NAME={_js_json(manifest_name)};"
        f"const DATA_BASES={_js_json(_DATA_BASES)};</script>"
    )
    out.write_text(
        _shell(
            rows,
            timeout_s,
            data_block,
            _JS_BOOT_CONSOLIDATED,
            families_override=families,
            solvers_override=all_solvers,
            domains_override=domains,
            default_solvers=sorted(defaults),
            solver_panel=_solver_panel(all_solvers, defaults),
        )
    )
    n_new = sum(1 for ss in new_shards.values() for f in ss if f not in before)
    print(
        f"updated {out} ({len(all_solvers)} solver versions, "
        f"{len(defaults)} default-on, {n_new} new shards)"
    )


def extract_inline_data(html_path: Path) -> list[dict]:
    """Pull the `DATA` array out of an inline-format report HTML, for
    migrating old reports to the split format."""
    import re

    src = html_path.read_text()
    m = re.search(r"const DATA\s*=\s*(\[.*?\]);", src, re.DOTALL)
    if not m:
        raise ValueError(f"{html_path}: no inline DATA block")
    return json.loads(m.group(1).replace("<\\/", "</"))
