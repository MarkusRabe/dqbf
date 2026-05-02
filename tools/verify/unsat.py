"""Self-contained UNSAT-proof checker.

Imports ONLY from `tools.verify.formats` and stdlib. The inference-rule
checks are implemented locally; nothing is shared with `provers/`.
"""

from __future__ import annotations

from tools.verify.formats import Clause, Formula, Proof


def var(lit: int) -> int:
    return abs(lit)


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


def _is_ureduction(f: Formula, src: Clause, dst: Clause) -> bool:
    """`dst` is reachable from `src` by zero or more sound ∀-reduction
    steps: every dropped literal is universal, its var is not in the
    existential-dep set of what remains, and its negation is not in
    `src`."""
    if not dst <= src:
        return False
    ed = _ex_deps(f, dst)
    for lit in src - dst:
        v = var(lit)
        if not f.is_universal(v) or v in ed or -lit in src:
            return False
    return True


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
    forks: dict[int, tuple[int, frozenset[int], frozenset[int], str]] = {}

    def prem(i: int) -> Clause | None:
        return derived[i] if 0 <= i < len(derived) else None

    for s in proof.steps:
        c = frozenset(s.clause)
        if s.rule == "axiom":
            if c not in g.clauses:
                return False
        elif s.rule == "res":
            if len(s.premises) != 2 or s.pivot is None:
                return False
            a, b = prem(s.premises[0]), prem(s.premises[1])
            if a is None or b is None:
                return False
            r = _resolve(a, b, s.pivot)
            if r is None or not _is_ureduction(g, r, c):
                return False
        elif s.rule == "ured":
            if len(s.premises) != 1:
                return False
            a = prem(s.premises[0])
            if a is None or not _is_ureduction(g, a, c):
                return False
        elif s.rule in ("fex", "sfex"):
            if len(s.premises) != 1 or s.part is None or s.fresh is None:
                return False
            src = prem(s.premises[0])
            if src is None:
                return False
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
            sig = (s.premises[0], part, c3, s.rule)
            if s.fresh in forks:
                if forks[s.fresh] != sig:
                    return False
            else:
                if s.fresh <= f.n_vars or s.fresh in g.dependencies or g.is_universal(s.fresh):
                    return False
                d1, d2 = _clause_dep(g, c1), _clause_dep(g, c2)
                drop = frozenset(var(lit) for lit in c3) if s.rule == "sfex" else frozenset()
                g = g.with_existential(s.fresh, (d1 & d2) - drop)
                forks[s.fresh] = sig
        else:
            return False
        derived.append(c)
    return frozenset() in derived
