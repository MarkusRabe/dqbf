"""Self-contained UNSAT-proof checker.

Imports ONLY `core.formula` (data) and `core.proof_trace` (format).
The inference-rule checks are re-implemented here so the trusted base
does not include `provers/`.
"""

from __future__ import annotations

from core.formula import Clause, Formula, var
from core.proof_trace import Proof


def _is_tautology(c: Clause) -> bool:
    return any(-lit in c for lit in c if lit > 0)


def _resolve(c1: Clause, c2: Clause, pivot: int) -> Clause | None:
    p = abs(pivot)
    if p in c1 and -p in c2:
        a, b = c1, c2
    elif -p in c1 and p in c2:
        a, b = c2, c1
    else:
        return None
    r = (a - {p}) | (b - {-p})
    return None if _is_tautology(r) else frozenset(r)


def _ex_deps(f: Formula, c: Clause) -> set[int]:
    out: set[int] = set()
    for lit in c:
        v = var(lit)
        if f.is_existential(v):
            out |= f.dependencies[v]
    return out


def _universal_reduce(f: Formula, c: Clause) -> Clause:
    cur = set(c)
    changed = True
    while changed:
        changed = False
        ed = _ex_deps(f, frozenset(cur))
        for lit in list(cur):
            v = var(lit)
            if f.is_universal(v) and v not in ed and -lit not in cur:
                cur.discard(lit)
                changed = True
    return frozenset(cur)


def _clause_dep(f: Formula, c: Clause) -> frozenset[int]:
    out: set[int] = set()
    for lit in c:
        v = var(lit)
        out |= f.dependencies[v] if f.is_existential(v) else {v}
    return frozenset(out)


def verify_proof(f: Formula, proof: Proof) -> bool:
    """Return True iff every step is a valid rule application and ⊥ is derived."""
    g = f
    derived: list[Clause] = []
    for s in proof.steps:
        c = frozenset(s.clause)
        if s.rule == "axiom":
            if c not in g.clauses:
                return False
        elif s.rule == "res":
            if len(s.premises) != 2 or s.pivot is None:
                return False
            r = _resolve(derived[s.premises[0]], derived[s.premises[1]], s.pivot)
            if r is None or _universal_reduce(g, r) != c:
                return False
        elif s.rule == "ured":
            if len(s.premises) != 1:
                return False
            if _universal_reduce(g, derived[s.premises[0]]) != c:
                return False
        elif s.rule in ("fex", "sfex"):
            if len(s.premises) != 1 or s.part is None or s.fresh is None:
                return False
            src = derived[s.premises[0]]
            part = frozenset(s.part)
            if not part <= src:
                return False
            c3 = frozenset(s.c3 or ())
            if s.rule == "sfex" and any(not g.is_universal(var(lit)) for lit in c3):
                return False
            c1, c2 = part, src - part
            left = c3 | c1 | {s.fresh}
            right = c3 | c2 | {-s.fresh}
            if c not in (left, right):
                return False
            if s.fresh > g.n_vars:
                d1, d2 = _clause_dep(g, c1), _clause_dep(g, c2)
                drop = frozenset(var(lit) for lit in c3) if s.rule == "sfex" else frozenset()
                g = g.add_existential(s.fresh, (d1 & d2) - drop)
            elif not g.is_existential(s.fresh):
                return False
        else:
            return False
        derived.append(c)
    return frozenset() in derived
