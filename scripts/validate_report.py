"""Validate the rendered consolidated report against the raw shard data.

The report's JS computes per-(solver, family) solved/total cells, the
cactus plot, the cert table, and disagreement counts. This script loads
the same shards, recomputes the headline numbers Python-side (mirroring
the JS logic, but written independently so a bug in one is caught by the
other), loads the report in a headless browser, and asserts the rendered
DOM matches.

Run after any change to `multi_report.py`'s rendering or
`make_report.py::archive`.

    python -m scripts.validate_report [--port 8765]
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "docs" / "dev_reports"
DATA = REPORTS / "data"

SOLVED = {"sat", "unsat"}
RAN = {"sat", "unsat", "unknown", "timeout"}
HANDLES = {
    "dqbf": {"dqbf", "qbf", "hwmc", "syntcomp"},
    "qbf": {"qbf"},
    "hwmc": {"hwmc"},
    "syntcomp": {"syntcomp"},
}


def load_shards(solvers: list[str], manifest: dict) -> list[dict]:
    rows: list[dict] = []
    for s in solvers:
        for f in manifest["solvers"].get(s, []):
            p = DATA / f
            if not p.exists():
                print(f"!! missing shard {f}", file=sys.stderr)
                continue
            rows.extend(json.loads(gzip.decompress(p.read_bytes())))
    return rows


def domain_sets(rows: list[dict], domains: dict[str, str], solvers: list[str]) -> tuple[dict, dict]:
    """Replicate `computeDomainSets()` from the report JS."""
    fams_for: dict[str, set[str]] = {}
    solvers_for: dict[str, list[str]] = {}
    for d in ("dqbf", "qbf", "hwmc", "syntcomp"):
        native = {s for s in solvers if domains.get(s) == d}
        fams = {r["family"] for r in rows if r["solver"] in native and r["got"] in RAN}
        fams_for[d] = fams
        solvers_for[d] = [
            s for s in solvers
            if d in HANDLES.get(domains.get(s, "dqbf"), set())
            and any(r["solver"] == s and r["family"] in fams and r["got"] in RAN for r in rows)
        ]
    return fams_for, solvers_for


def all_row(
    rows: list[dict],
    domain: str,
    fams_for: dict,
    solvers_for: dict,
    count_mode: str = "encodings",
    resf: str = "all",
) -> dict[str, tuple[int, int]]:
    """Replicate the famtree 'all' cell computation from `updateFamStats()`."""
    sv = solvers_for[domain]
    df = fams_for[domain]
    leaf: dict[str, set] = defaultdict(set)
    solved_key: dict[str, set] = {s: set() for s in sv}
    for r in rows:
        if r["family"] not in df or r["solver"] not in sv:
            continue
        if resf != "all" and r.get("expected") != resf:
            continue
        u = (r.get("problem_key") or r["path"]) if count_mode == "problems" else r["path"]
        leaf[r["family"]].add(u)
        if r["got"] in SOLVED:
            solved_key[r["solver"]].add(u)
    denom: set = set()
    for fam_units in leaf.values():
        denom |= fam_units
    out: dict[str, tuple[int, int]] = {}
    for s in sv:
        ok = sum(1 for u in denom if u in solved_key[s])
        out[s] = (ok, len(denom))
    return out


def cert_table(
    rows: list[dict],
    solvers: list[str],
    result: str,
    families: set[str],
) -> dict[str, dict]:
    """Replicate `certRowFor()` from the report JS, applied to each solver
    for one `result` ('sat' or 'unsat') over `families`. The JS renders
    two tables (SAT/UNSAT certificate verification)."""
    out: dict[str, dict] = {}
    for s in solvers:
        sr = [
            r for r in rows
            if r["solver"] == s and r["got"] == result and r["family"] in families
        ]
        n = len(sr)
        with_cert = valid = inv = skip = 0
        for r in sr:
            cs = r.get("cert_status") or "n/a"
            if cs != "n/a":
                with_cert += 1
            if cs == "valid":
                valid += 1
            elif cs in ("invalid", "dep", "error"):
                inv += 1
            elif cs in ("skipped", "timeout"):
                skip += 1
        out[s] = {"n": n, "with_cert": with_cert, "valid": valid, "inv": inv, "skip": skip}
    return out


def render_check(port: int = 8765) -> int:
    from playwright.sync_api import sync_playwright

    mf = json.loads((DATA / "report.manifest.json").read_text())
    src = (REPORTS / "report.html").read_text()
    m = re.search(r"let SOLVERS=(\[.*?\]);", src)
    assert m, "SOLVERS not found in report.html"
    default_solvers = json.loads(m.group(1))
    print(f"default solvers ({len(default_solvers)}): {default_solvers}")
    rows = load_shards(default_solvers, mf)
    print(f"loaded {len(rows)} rows from shards\n")

    fams_for, solvers_for = domain_sets(rows, mf["domains"], default_solvers)

    mismatches = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        msgs: list[str] = []
        pg.on("console", lambda m: msgs.append(m.text))
        pg.on("pageerror", lambda e: msgs.append(f"PAGEERROR: {e}"))
        pg.goto(f"http://localhost:{port}/report.html",
                wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(10000)

        n_data = pg.evaluate("DATA.length")
        if n_data != len(rows):
            print(f"!! DATA.length={n_data}, expected {len(rows)} ({len(rows)-n_data} missing)")
            mismatches += 1
        else:
            print(f"   ok DATA.length = {n_data}")

        for domain in ("dqbf", "qbf", "hwmc", "syntcomp"):
            if not solvers_for[domain]:
                # Domain pill should be disabled.
                disabled = pg.evaluate(f"document.querySelector('input[name=domain][value={domain}]').disabled")
                if not disabled:
                    print(f"!! domain {domain} should be disabled but isn't")
                    mismatches += 1
                continue
            pg.click(f"input[name=domain][value={domain}]")
            pg.wait_for_timeout(1500)
            for count_mode in ("encodings", "problems"):
                pg.click(f"input[name=count-overview][value={count_mode}]")
                pg.wait_for_timeout(800)
                expected = all_row(rows, domain, fams_for, solvers_for, count_mode)
                # Read the rendered 'all' row + header.
                rendered = pg.evaluate("""(()=>{
                  const hdr = document.querySelector('#famstats-hdr-overview');
                  const all = document.querySelector('.famrow[data-path=""] .famstats');
                  if(!hdr || !all) return {};
                  const svs = [...hdr.children].map(c=>c.textContent);
                  const out = {};
                  for(let i=0; i<svs.length; i++){
                    const txt = all.children[i] ? all.children[i].textContent : "";
                    const m = txt.match(/(\\d+)\\/(\\d+)/);
                    out[svs[i]] = m ? [parseInt(m[1]), parseInt(m[2])] : null;
                  }
                  return out;
                })()""")
                ok = True
                for s, (sv, tot) in sorted(expected.items()):
                    r = rendered.get(s)
                    if r != [sv, tot]:
                        print(f"!! {domain}/{count_mode}/all/{s}: rendered {r}, expected {sv}/{tot}")
                        mismatches += 1
                        ok = False
                if ok:
                    n_solvers = len(expected)
                    sample = sorted(expected.items())[0] if expected else ("", (0, 0))
                    pct = 100 * sample[1][0] // sample[1][1] if sample[1][1] else 0
                    print(f"   ok {domain}/{count_mode}: {n_solvers} solver columns "
                          f"(e.g. {sample[0]}={sample[1][0]}/{sample[1][1]} {pct}%)")

        # Cert tables (SAT + UNSAT) and disagreements on dqbf domain.
        pg.click("input[name=domain][value=dqbf]")
        pg.click("input[name=count-overview][value=encodings]")
        pg.wait_for_timeout(1500)
        for res_kind in ("SAT", "UNSAT"):
            expected_certs = cert_table(rows, solvers_for["dqbf"], res_kind.lower(), fams_for["dqbf"])
            rendered_certs = pg.evaluate(f"""(()=>{{
              const out = {{}};
              const h3 = [...document.querySelectorAll('#overview h3')]
                .find(h => h.textContent.startsWith("{res_kind} certificate"));
              if(!h3) return out;
              let t = h3.nextElementSibling;
              while(t && t.tagName !== "TABLE") t = t.nextElementSibling;
              if(!t) return out;
              for(const tr of t.querySelectorAll('tr')){{
                const tds = [...tr.children].map(c=>c.textContent.trim());
                if(tds.length < 6 || tds[0]==="solver") continue;
                out[tds[0]] = {{n: parseInt(tds[1]), with_cert: parseInt(tds[2]),
                               valid: parseInt(tds[3]), inv: parseInt(tds[4]),
                               skip: parseInt(tds[5])}};
              }}
              return out;
            }})()""")
            cert_ok = True
            for s, e in sorted(expected_certs.items()):
                if e["n"] == 0:
                    continue  # JS skips solvers with no rows
                r = rendered_certs.get(s)
                if r is None:
                    print(f"!! {res_kind}-cert/{s}: rendered missing, expected {e}")
                    mismatches += 1
                    cert_ok = False
                elif (r["n"] != e["n"] or r["valid"] != e["valid"] or r["inv"] != e["inv"]):
                    print(f"!! {res_kind}-cert/{s}: rendered {r}, expected {e}")
                    mismatches += 1
                    cert_ok = False
            if cert_ok:
                ne = sum(1 for e in expected_certs.values() if e["n"])
                print(f"   ok {res_kind} cert table: {ne} solvers")

        # Disagreement count.
        df = fams_for["dqbf"]
        sv_dqbf = set(solvers_for["dqbf"])
        rs = [r for r in rows if r["solver"] in sv_dqbf and r["family"] in df]
        by_inst: dict[str, set[str]] = defaultdict(set)
        for r in rs:
            if r["got"] in SOLVED:
                by_inst[r["path"]].add(r["got"])
        n_dis = sum(1 for v in by_inst.values() if len(v) > 1)
        rendered_dis = pg.evaluate("""(()=>{
          const h3 = [...document.querySelectorAll('#overview h3')]
            .find(h => h.textContent.startsWith("Disagreements"));
          if(!h3) return -1;
          const m = h3.textContent.match(/\\((\\d+)\\)/);
          return m ? parseInt(m[1]) : -1;
        })()""")
        if rendered_dis != n_dis:
            print(f"!! disagreements: rendered {rendered_dis}, expected {n_dis}")
            mismatches += 1
        else:
            print(f"   ok disagreements: {n_dis}")

        # JS errors are always a fail.
        errs = [m for m in msgs if "PAGEERROR" in m or "TypeError" in m or "ReferenceError" in m]
        if errs:
            print(f"!! {len(errs)} JS errors: {errs[:3]}")
            mismatches += len(errs)

        b.close()

    print(f"\n{'OK' if mismatches == 0 else 'FAIL'}: {mismatches} mismatches")
    return mismatches


if __name__ == "__main__":
    port = 8765
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    sys.exit(1 if render_check(port) else 0)
