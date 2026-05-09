"""Exploration: can extension variables strengthen BCE?

Propositional only — no quantifiers, no solvers. `python -m
scripts.bce_ext_explore` runs the examples and prints traces.
Write-up in `docs/notes/bce_ext.md`.
"""

from __future__ import annotations

import itertools
import random

Cl = frozenset[int]
CNF = list[Cl]


def cl(*lits: int) -> Cl:
    return frozenset(lits)


def is_taut(c: Cl) -> bool:
    return any(-l in c for l in c)


def resolve(c: Cl, d: Cl, lit: int) -> Cl:
    """C ⊗_lit D where lit ∈ C, ¬lit ∈ D."""
    return (c - {lit}) | (d - {-lit})


def is_blocked(f: CNF, c: Cl, lit: int) -> bool:
    """C blocked on lit ∈ C: every D ∋ ¬lit resolves to a tautology."""
    return all(is_taut(resolve(c, d, lit)) for d in f if d is not c and -lit in d)


def bce(f: CNF, *, trace: bool = False) -> CNF:
    """Blocked Clause Elimination to fixpoint. Confluent
    (Järvisalo-Biere-Heule, TACAS'10): result is order-independent."""
    work = list(f)
    while True:
        for i, c in enumerate(work):
            wit = next((l for l in c if is_blocked(work, c, l)), None)
            if wit is not None:
                if trace:
                    print(f"      remove {fmt(c)}  (blocked on {wit})")
                work.pop(i)
                break
        else:
            return work


def bce_random_order(f: CNF, seed: int) -> CNF:
    """BCE with a permuted scan order — for spot-checking confluence."""
    rng = random.Random(seed)
    work = list(f)
    rng.shuffle(work)
    while True:
        cands = [(i, l) for i, c in enumerate(work) for l in c if is_blocked(work, c, l)]
        if not cands:
            return work
        i, _ = rng.choice(cands)
        work.pop(i)


def tseitin(z: int, op: str, a: int, b: int) -> CNF:
    """Definitional clauses for z ↔ op(a, b)."""
    if op == "and":
        return [cl(z, -a, -b), cl(-z, a), cl(-z, b)]
    if op == "or":
        return [cl(-z, a, b), cl(z, -a), cl(z, -b)]
    if op == "xor":
        return [cl(-z, a, b), cl(-z, -a, -b), cl(z, -a, b), cl(z, a, -b)]
    raise ValueError(op)


def variables(f: CNF) -> list[int]:
    return sorted({abs(l) for c in f for l in c})


def fresh(f: CNF) -> int:
    vs = variables(f)
    return (max(vs) + 1) if vs else 1


def fmt(c: Cl) -> str:
    return "(" + " ".join(str(l) for l in sorted(c, key=abs)) + ")"


def fmt_cnf(f: CNF) -> str:
    return "  ".join(fmt(c) for c in f) or "⊤"


def canon(f: CNF) -> frozenset[Cl]:
    return frozenset(f)


# ── Theorem: pure addition of Def(z) never helps BCE ──────────────────


def check_pure_addition(n_random: int = 300, seed: int = 0) -> tuple[int, int]:
    """For random CNFs and every 2-input gate Def(z), verify
    BCE(F ∪ Def(z)) ∩ vars(F) == BCE(F).  Returns (trials, failures)."""
    rng = random.Random(seed)
    trials = failures = 0
    for _ in range(n_random):
        nv = rng.randint(2, 5)
        f: CNF = []
        for _ in range(rng.randint(2, 9)):
            c = cl(*{rng.choice((1, -1)) * rng.randint(1, nv) for _ in range(rng.randint(1, 3))})
            if not is_taut(c):
                f.append(c)
        if not f:
            continue
        base = canon(bce(f))
        # Confluence spot-check.
        for s in range(3):
            assert canon(bce_random_order(f, s)) == base, "BCE non-confluent?!"
        z = fresh(f)
        for a, b in itertools.combinations(variables(f), 2):
            for sa, sb, op in itertools.product((1, -1), (1, -1), ("and", "or", "xor")):
                if op == "xor" and (sa, sb) != (1, 1):
                    continue  # xor is sign-symmetric
                trials += 1
                aug = f + tseitin(z, op, sa * a, sb * b)
                rem = bce(aug)
                if any(z in c or -z in c for c in rem):
                    failures += 1  # def clause survived — shouldn't happen
                elif canon(rem) != base:
                    failures += 1
    return trials, failures


# ── Worked examples ───────────────────────────────────────────────────


def show(name: str, f: CNF, note: str = "") -> CNF:
    print(f"\n{name}: {fmt_cnf(f)}")
    if note:
        print(f"  {note}")
    rem = bce(f, trace=True)
    print(f"  → BCE fixpoint: {len(f)} → {len(rem)} clauses: {fmt_cnf(rem)}")
    return rem


def bva_grid(li: list[int], mj: list[int], z: int) -> CNF:
    """Manthey-Heule-Biere BVA grid factoring: {(li ∨ mj)}_{i,j} →
    {(z ∨ mj)}_j ∪ {(¬z ∨ li)}_i.  p·q clauses → p+q.  Equisatisfiable:
    F ≡ (⋀li) ∨ (⋀mj) ≡ ∃z. F'.  No Tseitin def added — z is implicit."""
    return [cl(z, m) for m in mj] + [cl(-z, l) for l in li]


def search_addition(f: CNF) -> None:
    """Exhaustive: try every 2-input Def(z) addition; report any that
    shrinks the BCE fixpoint (the theorem says none will)."""
    base = len(bce(f))
    z = fresh(f)
    found = False
    for a, b in itertools.combinations(variables(f), 2):
        for sa, sb, op in itertools.product((1, -1), (1, -1), ("and", "or", "xor")):
            rem = bce(f + tseitin(z, op, sa * a, sb * b))
            rem_orig = [c for c in rem if z not in c and -z not in c]
            if len(rem_orig) < base:
                found = True
                print(f"      z↔{op}({sa*a},{sb*b}): {base} → {len(rem_orig)}  !!")
    if not found:
        print(f"      no Def(z) addition shrinks the fixpoint (stays at {base})")


def main() -> None:
    print("═" * 72)
    print("Can extension variables strengthen BCE?")
    print("═" * 72)

    print("\n[1] Theorem check: adding a fresh Def(z) and nothing else never helps.")
    print("    Reason: every Def(z) clause is blocked on its z-literal, and z is")
    print("    fresh, so BCE removes Def(z) first (confluence + monotonicity).")
    trials, fails = check_pure_addition()
    print(f"    Empirical: {trials} (CNF, gate) pairs tested, {fails} counterexamples.")

    print("\n[2] Worked examples.")

    # 2a: SAT, BCE-stuck. Implication 3-cycle: a→c, c→¬b, ¬b→a (and a→¬b
    # via ¬a∨b? no). Actually ¬a→b, b→¬c, ¬c→? — every clause has a
    # non-tautological resolvent on every literal.
    stuck = [cl(1, 2), cl(-1, 3), cl(-2, -3)]
    show("2a. SAT, BCE-stuck (implication ring)", stuck,
         "a∨b, ¬a∨c, ¬b∨¬c — SAT (a=F,b=T,c=F), no clause blocked.")
    print("    exhaustive Def(z) search:")
    search_addition(stuck)

    # 2b: PHP(2,1). UNSAT — BCE preserves SAT, so it can never empty an
    # UNSAT formula. Extension can't change that.
    php = [cl(1), cl(2), cl(-1, -2)]
    show("2b. PHP(2,1), UNSAT", php,
         "p1, p2, ¬p1∨¬p2 — BCE is SAT-preserving; can never empty this.")
    print("    exhaustive Def(z) search:")
    search_addition(php)

    # 2c: exactly-one. BCE *already* solves this (the ALO clause is
    # blocked on every literal, since AMO clauses provide complements).
    eo = [cl(1, 2, 3), cl(-1, -2), cl(-1, -3), cl(-2, -3)]
    show("2c. exactly-one(a,b,c)", eo, "BCE alone empties it — no extension needed.")

    # 2d: a Tseitin chain x=a∧b, y=a∨b, x↔¬y. SAT (a≠b satisfies it).
    # BCE empties it — the gate clauses + top-level constraint together
    # form a blocked set. (Tseitin encodings of a circuit with a free
    # output are always BCE-eliminable.)
    miter_sat = (
        tseitin(4, "and", 1, 2)   # x = 4 = a∧b
        + tseitin(5, "or", 1, 2)  # y = 5 = a∨b
        + [cl(4, 5), cl(-4, -5)]  # x ↔ ¬y  (= a≠b)
    )
    show("2d. Tseitin x=a∧b, y=a∨b, x↔¬y (SAT: a≠b)", miter_sat,
         "BCE alone empties it — gate clauses + constraint form a blocked chain.")

    # 2e: a Tseitin miter that's UNSAT: x=a∧b, y=a∨b, x ∧ ¬y. BCE peels
    # the gate clauses but the surviving core encodes the contradiction.
    miter_unsat = (
        tseitin(4, "and", 1, 2)
        + tseitin(5, "or", 1, 2)
        + [cl(4), cl(-5)]  # x ∧ ¬y  ⇒  (a∧b) ∧ ¬(a∨b)  — UNSAT
    )
    show("2e. miter x=a∧b, y=a∨b, x∧¬y (UNSAT)", miter_unsat,
         "BCE peels gate clauses but cannot empty an UNSAT formula.")
    print("    exhaustive Def(z) search:")
    search_addition(miter_unsat)

    print("\n[3] The positive analogue: BVA — rewrite using z, then BCE.")
    print("    BVA replaces a p×q grid {(li∨mj)} with p+q clauses; this is")
    print("    *introducing-and-using* z, not just adding Def(z).")

    li, mj = [1, 2], [3, 4, 5]
    extra = [cl(-1, -2), cl(-3, -4, -5)]  # keep BCE from vacuously firing
    grid = [cl(a, b) for a in li for b in mj] + extra
    rem_grid = show("3a. 2×3 grid + constraints", grid)
    z = fresh(grid)
    factored = bva_grid(li, mj, z) + extra
    rem_fac = show("3b. same, BVA-factored on z (=¬⋁li ?)", factored,
                   "z 'selects' a row; F' ≡ ∃z.F' ≡ F.")
    print(f"\n    BVA shrank {len(grid)}→{len(factored)} before BCE; "
          f"BCE removed {len(grid)-len(rem_grid)} vs {len(factored)-len(rem_fac)} extra.")
    print("    Gain is from the *rewrite*, not from BCE seeing more.")

    print("\n[4] When DOES extension genuinely create new blocked literals?")
    print("    Only by *replacing* a non-tautological resolvent partner.")
    print("    Pure addition adds resolvent partners (more constraints to block)")
    print("    or adds nothing visible to old clauses (z is fresh) — never helps.")
    print()
    print("    Concretely: C blocked on l needs *every* D∋¬l to have ¬p for")
    print("    some p∈C\\{l}. Adding clauses only adds D's. To make C blocked,")
    print("    you must REMOVE or REWRITE the offending D — which is BVA, BVE,")
    print("    or resolution, not plain extension.")

    print("\n[5] DQBF lift (where extension DOES help blocked-ness).")
    print("    DQBF-BCE blocks C on l iff resolvents are taut AND the witness")
    print("    p has dep(p) ⊆ dep(l). FEx introduces a fresh ∃ with the")
    print("    *intersection* of two dep sets — a strictly smaller dep set than")
    print("    any original variable. So a clause never blockable on any original")
    print("    var (no var has a small enough dep) CAN become blockable on the")
    print("    fork var. Propositionally dep=all so this trivializes; it's a")
    print("    purely quantified phenomenon. This is why FEx exists in fork-res.")


if __name__ == "__main__":
    main()
