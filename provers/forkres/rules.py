"""Fork-resolution inference rules.

Each rule is a pure function. See OVERVIEW.md and
docs/references/fork_resolution_journal/main.tex for the formal
definitions; the journal version (Strong Fork Extension) is
authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.formula import Clause, Formula, Lit, var


def is_tautology(c: Clause) -> bool:
    return any(-lit in c for lit in c if lit > 0)


def resolve(c1: Clause, c2: Clause, pivot: int) -> Clause | None:
    """Resolution on variable `pivot`.

    Requires `pivot in c1` and `-pivot in c2` (or vice versa). Returns
    None if the side condition fails or the resolvent is a tautology.
    """
    p = abs(pivot)
    if p in c1 and -p in c2:
        pos, negc = c1, c2
    elif -p in c1 and p in c2:
        pos, negc = c2, c1
    else:
        return None
    r = (pos - {p}) | (negc - {-p})
    return None if is_tautology(r) else frozenset(r)


def universal_reduce(f: Formula, c: Clause) -> Clause:
    """Exhaustively apply ∀-reduction to clause `c`.

    Drop a universal literal ℓ if var(ℓ) ∉ dep(e) for every existential
    literal e in the clause and ¬ℓ ∉ c. Iterate to a fixpoint.
    """
    cur = set(c)
    changed = True
    while changed:
        changed = False
        ex_deps: set[int] = set()
        for lit in cur:
            v = var(lit)
            if f.is_existential(v):
                ex_deps |= f.dependencies[v]
        for lit in list(cur):
            v = var(lit)
            if f.is_universal(v) and v not in ex_deps and -lit not in cur:
                cur.discard(lit)
                changed = True
    return frozenset(cur)


@dataclass(frozen=True)
class ForkResult:
    formula: Formula
    fresh: int
    left: Clause
    right: Clause


def _split_dep(
    f: Formula, c: Clause, part: frozenset[Lit]
) -> tuple[frozenset[int], frozenset[int]]:
    c1 = frozenset(part)
    c2 = frozenset(c - part)
    return f.clause_dep(c1), f.clause_dep(c2)


def fork_extend(f: Formula, c: Clause, part: frozenset[Lit]) -> ForkResult:
    """FEx: from C=C₁∨C₂ derive (C₁∨x)∧(C₂∨¬x) with x fresh,
    dep(x) = dep(C₁) ∩ dep(C₂).
    """
    if not part <= c:
        raise ValueError("partition must be a subset of the clause")
    c1 = frozenset(part)
    c2 = frozenset(c - part)
    d1, d2 = _split_dep(f, c, part)
    x = f.n_vars + 1
    g = f.add_existential(x, d1 & d2)
    return ForkResult(formula=g, fresh=x, left=c1 | {x}, right=c2 | {-x})


def strong_fork_extend(
    f: Formula, c: Clause, part: frozenset[Lit], c3: frozenset[Lit]
) -> ForkResult:
    """SFEx: from C=C₁∨C₂ derive (C₃∨C₁∨x)∧(C₃∨C₂∨¬x) with x fresh,
    dep(x) = (dep(C₁) ∩ dep(C₂)) ∖ {var(ℓ) : ℓ ∈ C₃}. C₃ must be
    universal literals only.
    """
    for lit in c3:
        if not f.is_universal(var(lit)):
            raise ValueError(f"C3 literal {lit} is not universal")
    c1 = frozenset(part)
    c2 = frozenset(c - part)
    d1, d2 = _split_dep(f, c, part)
    drop = frozenset(var(lit) for lit in c3)
    x = f.n_vars + 1
    g = f.add_existential(x, (d1 & d2) - drop)
    return ForkResult(formula=g, fresh=x, left=c3 | c1 | {x}, right=c3 | c2 | {-x})


def resolvents(f: Formula, c1: Clause, c2: Clause) -> list[Clause]:
    """All non-tautological, ∀-reduced resolvents of c1, c2."""
    out: list[Clause] = []
    for lit in c1:
        if -lit in c2:
            r = resolve(c1, c2, var(lit))
            if r is not None:
                out.append(universal_reduce(f, r))
    return out


def find_information_fork(f: Formula, c: Clause) -> tuple[int, int] | None:
    """Return a pair of existential vars in `c` with incomparable deps, or None."""
    exs = [var(lit) for lit in c if f.is_existential(var(lit))]
    for i, a in enumerate(exs):
        for b in exs[i + 1 :]:
            da, db = f.dependencies[a], f.dependencies[b]
            if not (da <= db or db <= da):
                return (a, b)
    return None
