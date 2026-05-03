"""Render a multi-solver benchmark JSONL to a self-contained HTML report.

Three tabs (Overview / Single solver / Compare), each with its own
family + result filter, all driven by inline vanilla JS over an
embedded copy of the result rows. Single file, no external assets,
works offline.
"""

from __future__ import annotations

import html as _html
import json
from collections import defaultdict
from pathlib import Path

from benchmarks.runner.solvers import registry

DOMAIN_ORDER = ["dqbf", "qbf", "hwmc", "syntcomp"]

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
    "#domain{position:sticky;top:0;background:#fff;padding:.4em 0 0;z-index:2;"
    "font-size:.9em;border-bottom:1px solid #eee}"
    "#domain label{margin-right:1em;cursor:pointer}"
    "#domain b{margin-right:.6em}"
    "#tabs{position:sticky;top:1.9em;background:#fff;padding:.4em 0;z-index:1}"
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
    "ul.famtree,ul.famtree ul{list-style:none;margin:0;padding-left:1em}"
    "ul.famtree>li{padding-left:0}"
    "ul.famtree li{line-height:1.5}"
    ".famtree ul.folded{display:none}"
    ".famfold{display:inline-block;width:1em;text-align:center;cursor:pointer;"
    "font-family:ui-monospace,monospace;user-select:none;color:#666}"
    ".famfold-none{cursor:default;color:transparent}"
    "a.famonly{font-size:.8em;color:#888;margin-left:.4em;cursor:pointer;"
    "text-decoration:none}a.famonly:hover{text-decoration:underline;color:#555}"
    ".ctl fieldset.families{max-height:16em;overflow:auto;min-width:14em}"
)


def load(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _esc(x: object) -> str:
    return _html.escape(str(x), quote=True)


def _js_json(obj: object) -> str:
    # Prevent </script> breakout inside the inline data block.
    return json.dumps(obj).replace("</", "<\\/")


# Only the fields the JS needs — keeps the embedded blob small.
_JS_FIELDS = ("solver", "path", "family", "expected", "got", "wall_s", "cert_status", "cert_bytes")


def _opts(solvers: list[str], selected: str = "") -> str:
    return "".join(
        f'<option value="{_esc(s)}"{" selected" if s == selected else ""}>{_esc(s)}</option>'
        for s in solvers
    )


def _family_tree(scope: str, families: list[str]) -> str:
    """Nested <ul class="famtree"> with one checkbox per node + an 'only' link.

    Leaf checkboxes carry class=famchk-<scope> and value=<full family path>
    so the existing state(scope) JS keeps working unchanged. Interior
    checkboxes use class=famint-<scope> and have no value.
    """
    # Build a trie: node = {"_leaf": str|None, children: {seg: node}}
    root: dict = {"_leaf": None, "ch": {}}
    for fam in sorted(families):
        cur = root
        for seg in fam.split("/"):
            cur = cur["ch"].setdefault(seg, {"_leaf": None, "ch": {}})
        cur["_leaf"] = fam

    def emit(label: str, node: dict) -> str:
        leaf = node["_leaf"]
        kids = node["ch"]
        if leaf is not None:
            cb = f'<input type="checkbox" class="famchk-{scope}" value="{_esc(leaf)}" checked>'
        else:
            cb = f'<input type="checkbox" class="famint-{scope}" checked>'
        if kids:
            fold = '<span class="famfold">▸</span>'
            sub = (
                '<ul class="folded">'
                + "".join(emit(k, v) for k, v in sorted(kids.items()))
                + "</ul>"
            )
        else:
            fold = '<span class="famfold famfold-none">·</span>'
            sub = ""
        return f'<li>{fold}{cb} {_esc(label)} <a class="famonly">only</a>{sub}</li>'

    inner = "".join(emit(k, v) for k, v in sorted(root["ch"].items()))
    return (
        f'<ul class="famtree" data-scope="{scope}">'
        f'<li><span class="famfold">▾</span>'
        f'<input type="checkbox" class="famint-{scope}" checked> all '
        f'<a class="famonly">only</a><ul>{inner}</ul></li></ul>'
    )


def _local_controls(scope: str, families: list[str], extra: str) -> str:
    return f"""
<div class="ctl">
  <fieldset class="families"><legend>families</legend>{_family_tree(scope, families)}</fieldset>
  <fieldset><legend>result</legend>
    <label><input type="radio" name="resf-{scope}" value="all" checked> all</label>
    <label><input type="radio" name="resf-{scope}" value="sat"> sat</label>
    <label><input type="radio" name="resf-{scope}" value="unsat"> unsat</label>
  </fieldset>
  {extra}
</div>
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
  return {fams, resf};
}
function rowsAll(st){
  const ds = new Set(dSolvers()), df = dFams();
  return DATA.filter(r =>
    ds.has(r.solver) && df.has(r.family) &&
    st.fams.has(r.family) && (st.resf === "all" || r.expected === st.resf));
}
function rowsFor(solver, st){
  return rowsAll(st).filter(r => r.solver === solver);
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

function cactus(rs){
  const W=520,H=320;
  const SV = dSolvers();
  const times = {};
  for (const s of SV)
    times[s] = rs.filter(r=>r.solver===s && SOLVED.has(r.got)).map(r=>r.wall_s).sort((a,b)=>a-b);
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
  const SV = dSolvers(), df = dFams();
  const root = $("#overview"); root.textContent = "";
  const fams = FAMILIES.filter(f=>st.fams.has(f) && df.has(f));

  // per-family % solved
  const nInst = {}; // family -> #unique paths
  for (const f of fams)
    nInst[f] = new Set(rs.filter(r=>r.family===f).map(r=>r.path)).size;
  const famRows = fams.map(f=>{
    const cells=[f];
    for (const s of SV){
      const ok = rs.filter(r=>r.family===f && r.solver===s && SOLVED.has(r.got)).length;
      const n = nInst[f]||0;
      cells.push(n?`${ok}/${n} (${Math.round(100*ok/n)}%)`:"-");
    }
    return cells;
  });
  root.appendChild(el("h3",{text:"% solved per family"}));
  root.appendChild(tbl(["family",...SV], famRows));

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
  root.appendChild(cactus(rs));

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
    // bottom-up: each interior reflects its descendant leaves
    const ints = Array.from(tree.querySelectorAll(".famint-"+scope)).reverse();
    for(const cb of ints){
      const ls = leavesOf(cb.closest("li"));
      const on = ls.filter(l=>l.checked).length;
      cb.checked = on===ls.length && ls.length>0;
      cb.indeterminate = on>0 && on<ls.length;
    }
  }
  // interior toggle => set all descendant leaves
  for(const cb of tree.querySelectorAll(".famint-"+scope)){
    cb.addEventListener("change", ()=>{
      const li = cb.closest("li");
      for(const l of leavesOf(li)) l.checked = cb.checked;
      for(const i of interiorsOf(li)) { i.checked = cb.checked; i.indeterminate=false; }
      syncInterior(); render();
    });
  }
  // leaf change => resync interior
  for(const cb of tree.querySelectorAll(".famchk-"+scope)){
    cb.addEventListener("change", ()=>{ syncInterior(); render(); });
  }
  // fold/unfold toggle on interior nodes
  function setFold(li, folded){
    const ul = li.querySelector(":scope > ul");
    const tg = li.querySelector(":scope > .famfold");
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
  // 'only' => uncheck all leaves in scope, check leaves under this <li>, expand it
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

// Domain → families: families where at least one *native* solver of that
// domain produced a non-"n/a" result. Then domain → solvers: every solver
// (native or not) with a non-"n/a" result on at least one of those families.
const FAMS_FOR = {}, SOLVERS_FOR = {};
for(const d of DOMAIN_NAMES){
  const native = new Set(SOLVERS.filter(s=>DOMAINS[s]===d));
  const fams = new Set(
    DATA.filter(r=>native.has(r.solver) && r.got!=="n/a").map(r=>r.family));
  FAMS_FOR[d] = fams;
  SOLVERS_FOR[d] = SOLVERS.filter(s=>
    DATA.some(r=>r.solver===s && fams.has(r.family) && r.got!=="n/a"));
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
      if(li.querySelector(":scope > input.famchk-"+scope)) continue; // leaf handled
      const vis = [...li.querySelectorAll(".famchk-"+scope)]
        .some(l=>l.closest("li").style.display!=="none");
      li.style.display = vis ? "" : "none";
    }
  }
  renderOverview(); renderSingle(); renderPair();
}

document.addEventListener("DOMContentLoaded",()=>{
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
});
"""


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


def render(rows: list[dict], out: Path, timeout_s: float) -> None:
    solvers = sorted({r["solver"] for r in rows})
    families = sorted({r["family"] for r in rows})
    reg = registry()
    domains = {s: (reg[s].domain if s in reg else "dqbf") for s in solvers}

    slim = [{k: r.get(k) for k in _JS_FIELDS} for r in rows]
    data_block = (
        "<script>"
        f"const DATA={_js_json(slim)};"
        f"const SOLVERS={_js_json(solvers)};"
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

    overview_ctl = _local_controls("overview", families, "")
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
{_warnings(rows, solvers)}
{data_block}
{_domain_selector(domains)}
{tabs_nav}
<section id="tab-overview" class="tab panel">{overview_ctl}<div id="overview"></div></section>
<section id="tab-single" class="tab panel">{single_ctl}<div id="single"></div></section>
<section id="tab-compare" class="tab panel">{pair_ctl}<div id="pair"></div></section>
<script>{_JS}</script>
"""
    out.write_text(html)
    print(f"wrote {out}")
