"""Collatz v2: more encodings, more step functions, higher widths.

The v1 family covers ``unrolled`` and ``succinct`` at small widths via
EQFOB.  v2 adds (a) a step-counter-only DQBF that drops the ``∀x``
prefix, (b) alternate step-function bit-blastings, (c) widths up to 64,
and (d) an inductive-invariant encoding for the *no-overflow* safety
property via ``tools.hwmc2dqbf_indinv``.

The ``succinct``/``tonly``/``indinv`` encodings are built by **direct
CNF** (not EQFOB).  EQFOB's ``fun`` bitblast produces formulas that
dqbdd/hqs both decide UNSAT where pedant and a hand-crafted equivalent
both decide SAT — see ``generate_test.py::test_eqfob_fun_disagreement``
for a minimal repro.  Until that's resolved, only the
function-application-free ``unrolled`` encoding goes through EQFOB.

Encodings
---------
``unrolled``         ∀x. ∃s_0..s_K.  K explicit steps (∀∃-QBF). EQFOB.
``succinct``         ∃f(x,t). ∀x,t,t'.  step counter is K bits ⇒ 2^K-1
                     steps. SAT ⇔ every nonzero N-bit start reaches 1.
``tonly``            ∃f(t). ∀t,t'.  one trajectory; SAT ⇔ some start
                     needs ≥ 2^K steps. |U| = 2K — independent of N.
``indinv``           via ``encode_indinv``: state=bv[N], T=Collatz step,
                     init = (start < 2^⌈N/2⌉), bad = top bit set. SAT ⇔
                     an invariant proves small starts never overflow.

Step variants
-------------
``shift``            3v+1 as ``(v<<1)+v+1``         (v1's choice)
``mul``              3v+1 as ``v + 2v + 1``         (separate adder chain)
``shortcut``         odd ↦ (3v+1)/2, even ↦ v/2    (accelerated map)
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import click

from core import dqdimacs
from core.formula import Formula, make_formula
from tools.eqfob.eqfob.bitblast import bitblast
from tools.eqfob.eqfob.parse import parse
from tools.eqfob.eqfob.typecheck import check
from tools.hwmc2dqbf_indinv.encode import Transition, encode_indinv

VAR_CAP = 50_000

GRID_UNROLLED = [(n, k) for n in (16, 24, 32, 48, 64) for k in (8, 12, 16)]
GRID_SUCCINCT = [(n, k) for n in (16, 24, 32, 48, 64) for k in (6, 8, 10)]
GRID_TONLY = [(n, k) for n in (16, 24, 32, 48, 64) for k in (6, 8, 10, 12)]
GRID_INDINV = [(n, (n + 1) // 2) for n in (8, 12, 16, 24, 32, 48, 64)]

STEPS = ("shift", "mul", "shortcut")


# ---- Shared CNF builder ---------------------------------------------------


class _Cnf:
    """Tiny Tseitin builder with explicit dependency tracking."""

    def __init__(self) -> None:
        self.universals: list[int] = []
        self.deps: dict[int, frozenset[int]] = {}
        self.clauses: list[list[int]] = []
        self._n = 0
        self.TRUE = self.fe(frozenset())
        self.clauses.append([self.TRUE])

    def fu(self) -> int:
        self._n += 1
        self.universals.append(self._n)
        return self._n

    def fe(self, d: frozenset[int]) -> int:
        self._n += 1
        self.deps[self._n] = d
        return self._n

    def g_and(self, a: int, b: int, d: frozenset[int]) -> int:
        if a == self.TRUE:
            return b
        if b == self.TRUE:
            return a
        if a == -self.TRUE or b == -self.TRUE:
            return -self.TRUE
        g = self.fe(d)
        self.clauses.extend(([-g, a], [-g, b], [g, -a, -b]))
        return g

    def g_xor(self, a: int, b: int, d: frozenset[int]) -> int:
        g = self.fe(d)
        self.clauses.extend(([-g, a, b], [-g, -a, -b], [g, -a, b], [g, a, -b]))
        return g

    def g_iff(self, a: int, b: int, d: frozenset[int]) -> int:
        return -self.g_xor(a, b, d)

    def big_and(self, xs: list[int], d: frozenset[int]) -> int:
        if not xs:
            return self.TRUE
        if len(xs) == 1:
            return xs[0]
        g = self.fe(d)
        for x in xs:
            self.clauses.append([-g, x])
        self.clauses.append([g] + [-x for x in xs])
        return g

    def add(self, a: list[int], b: list[int], cin: int, d: frozenset[int]) -> list[int]:
        out: list[int] = []
        c = cin
        for ai, bi in zip(a, b, strict=True):
            axb = self.g_xor(ai, bi, d)
            out.append(self.g_xor(axb, c, d))
            t1 = self.g_and(ai, bi, d)
            t2 = self.g_and(c, axb, d)
            cn = self.fe(d)
            self.clauses.extend(([-cn, t1, t2], [cn, -t1], [cn, -t2]))
            c = cn
        return out

    def mux(self, sel: int, a: list[int], b: list[int], d: frozenset[int]) -> list[int]:
        out: list[int] = []
        for ai, bi in zip(a, b, strict=True):
            g = self.fe(d)
            self.clauses.extend(
                ([-g, -sel, ai], [-g, sel, bi], [g, -sel, -ai], [g, sel, -bi])
            )
            out.append(g)
        return out

    def formula(self, comments: tuple[str, ...] = ()) -> Formula:
        return make_formula(self.universals, self.deps, self.clauses, comments)


def _collatz_step(c: _Cnf, s: list[int], step: str, d: frozenset[int]) -> list[int]:
    """Bit-blast one Collatz step (with sticky {0,1}→1 sink) over `s`."""
    n = len(s)
    F = -c.TRUE
    even_next = s[1:] + [F]
    shl = [F] + s[:-1]
    if step == "mul":
        three_v = c.add(s, shl, F, d)
        odd_full = c.add(three_v, [F] * n, c.TRUE, d)
    else:
        odd_full = c.add(shl, s, c.TRUE, d)
    odd_next = (odd_full[1:] + [F]) if step == "shortcut" else odd_full
    odd = s[0]
    hi = F
    for b in s[1:]:
        nh = c.fe(d)
        c.clauses.extend(([-nh, hi, b], [nh, -hi], [nh, -b]))
        hi = nh
    le1 = -hi
    one = [c.TRUE] + [F] * (n - 1)
    branch = c.mux(odd, odd_next, even_next, d)
    return c.mux(le1, one, branch, d)


# ---- Direct-CNF encodings -------------------------------------------------


def encode_tonly(n: int, k: int, step: str) -> Formula:
    """∃f:bv[K]→bv[N]. ∀t,t'. (t==t' → f@t==f@t') ∧
    (t'==t+1 ∧ t'≠0 → f@t' == step(f@t)) ∧ f@t∉{0,1}."""
    c = _Cnf()
    t = [c.fu() for _ in range(k)]
    tp = [c.fu() for _ in range(k)]
    dt, dtp = frozenset(t), frozenset(tp)
    dboth = dt | dtp
    F = -c.TRUE

    ft = [c.fe(dt) for _ in range(n)]
    ftp = [c.fe(dtp) for _ in range(n)]

    EQ = c.big_and([c.g_iff(a, b, dboth) for a, b in zip(t, tp, strict=True)], dboth)
    for a, b in zip(ft, ftp, strict=True):
        c.clauses.extend(([-EQ, -a, b], [-EQ, a, -b]))

    inc = c.add(t, [F] * k, c.TRUE, dt)
    SUCC = c.big_and([c.g_iff(a, b, dboth) for a, b in zip(tp, inc, strict=True)], dboth)
    tp_nz = c.fe(dtp)
    c.clauses.append([-tp_nz] + list(tp))
    for b in tp:
        c.clauses.append([tp_nz, -b])
    guard = c.g_and(SUCC, tp_nz, dboth)

    nx = _collatz_step(c, ft, step, dt)
    for a, b in zip(ftp, nx, strict=True):
        c.clauses.extend(([-guard, -a, b], [-guard, a, -b]))

    c.clauses.append(list(ft))  # f(t) ≠ 0
    c.clauses.append([-ft[0]] + ft[1:])  # f(t) ≠ 1

    return c.formula(
        comments=(f"collatz enc=tonly step={step} N={n} K={k}",)
    )


def encode_succinct(n: int, k: int, step: str) -> Formula:
    """∃f:bv[N]×bv[K]→bv[N]. ∀x,t,t'. f(x,0)=x ∧ chain ∧ reach-1."""
    c = _Cnf()
    x = [c.fu() for _ in range(n)]
    t = [c.fu() for _ in range(k)]
    tp = [c.fu() for _ in range(k)]
    dx, dt, dtp = frozenset(x), frozenset(t), frozenset(tp)
    dxt, dxtp = dx | dt, dx | dtp
    dboth = dxt | dtp
    F = -c.TRUE

    fxt = [c.fe(dxt) for _ in range(n)]
    fxtp = [c.fe(dxtp) for _ in range(n)]

    EQ = c.big_and([c.g_iff(a, b, dt | dtp) for a, b in zip(t, tp, strict=True)], dt | dtp)
    for a, b in zip(fxt, fxtp, strict=True):
        c.clauses.extend(([-EQ, -a, b], [-EQ, a, -b]))

    t_zero = c.big_and([-b for b in t], dt)
    for xi, fi in zip(x, fxt, strict=True):
        c.clauses.extend(([-t_zero, -xi, fi], [-t_zero, xi, -fi]))

    inc = c.add(t, [F] * k, c.TRUE, dt)
    SUCC = c.big_and([c.g_iff(a, b, dt | dtp) for a, b in zip(tp, inc, strict=True)], dt | dtp)
    tp_nz = c.fe(dtp)
    c.clauses.append([-tp_nz] + list(tp))
    for b in tp:
        c.clauses.append([tp_nz, -b])
    guard = c.g_and(SUCC, tp_nz, dboth)

    nx = _collatz_step(c, fxt, step, dxt)
    for a, b in zip(fxtp, nx, strict=True):
        c.clauses.extend(([-guard, -a, b], [-guard, a, -b]))

    # (t = 2^K-1) → (x=0 ∨ f(x,t)=1)
    t_max = c.big_and(list(t), dt)
    x_nz = c.fe(dx)
    c.clauses.append([-x_nz] + list(x))
    for b in x:
        c.clauses.append([x_nz, -b])
    f_is_one = c.big_and([fxt[0]] + [-b for b in fxt[1:]], dxt)
    c.clauses.append([-t_max, -x_nz, f_is_one])

    return c.formula(
        comments=(f"collatz enc=succinct step={step} N={n} K={k}",)
    )


# ---- EQFOB-based unrolled (no `fun`, so safe) -----------------------------


def _step_expr(v: str, step: str) -> str:
    if step == "mul":
        odd = f"(3 * {v}) + 1"
    elif step == "shortcut":
        odd = f"(({v} << 1) + {v} + 1) >>> 1"
    else:
        odd = f"({v} << 1) + {v} + 1"
    return f"ite({v} <= 1, ({v} & 0) + 1, ite(({v} & 1) == 0, {v} >>> 1, {odd}))"


def eqfob_unrolled(n: int, k: int, step: str) -> str:
    lines = [
        f"-- Collatz v2 unrolled: every {n}-bit start reaches 1 in <= {k} steps?",
        f"param N = {n}",
        "forall x : bv[N]",
    ]
    lines += [f"exists s{i} : bv[N]" for i in range(k + 1)]
    lines.append("s0 == x")
    for i in range(k):
        lines.append(f"s{i + 1} == {_step_expr(f's{i}', step)}")
    reach = " || ".join(f"(s{i} == 1)" for i in range(k + 1))
    lines.append(f"(x == 0) || {reach}")
    return "\n".join(lines) + "\n"


# ---- Transition for indinv ------------------------------------------------


def collatz_transition(n: int, step: str) -> Transition:
    c = _Cnf()
    # _Cnf created TRUE as var 1; we want state at the front for clarity,
    # but Transition doesn't care about ordering — just IDs.
    s = [c.fe(frozenset()) for _ in range(n)]
    sp = [c.fe(frozenset()) for _ in range(n)]
    nx = _collatz_step(c, s, step, frozenset())
    trans: list[list[int]] = []
    for spi, nxi in zip(sp, nx, strict=True):
        trans.extend(([-spi, nxi], [spi, -nxi]))
    m = (n + 1) // 2
    return Transition(
        n_vars=c._n,
        state=s,
        inputs=[],
        next_state=sp,
        init=[-s[i] for i in range(m, n)],
        defs=c.clauses,
        trans=trans,
        bad=s[n - 1],
        comments=(f"collatz step={step} N={n} init=<2^{m} bad=bit{n - 1}",),
    )


# ---- Expected results from construction ----------------------------------

# 27 needs 111 ordinary / 70 shortcut steps (integer Collatz). For n≥16,
# 27's trajectory peaks at 9232 < 2^14 so the modular and integer maps
# agree; the bound below is exact there.
_NEED = {"shift": 111, "mul": 111, "shortcut": 70}


def known_expected(enc: str, step: str, n: int, k: int) -> str:
    if n < 16:
        return "unknown"
    need = _NEED[step]
    if enc == "unrolled" and k < need:
        return "unsat"
    if enc == "tonly" and (1 << k) - 1 < need:
        return "sat"
    return "unknown"


# ---- Driver ---------------------------------------------------------------


def _compile_eqfob(src: str) -> Formula:
    return bitblast(check(parse(src)))


_DIRECT = {"tonly": encode_tonly, "succinct": encode_succinct}
_GRID = {"unrolled": GRID_UNROLLED, "succinct": GRID_SUCCINCT, "tonly": GRID_TONLY}


@click.command()
@click.option("--out", type=click.Path(), default="benchmarks/train/collatz")
@click.option("--steps", default="shift,mul,shortcut")
def main(out: str, steps: str) -> None:
    base = Path(out)
    step_variants = [s for s in steps.split(",") if s in STEPS]
    skipped: list[str] = []

    def emit(
        variant: str, name: str, f: Formula, expected: str, problem_key: str, params: dict
    ) -> dict | None:
        d = base / variant
        d.mkdir(parents=True, exist_ok=True)
        if f.n_vars > VAR_CAP:
            skipped.append(f"{variant}/{name} ({f.n_vars} vars)")
            return None
        with gzip.open(d / f"{name}.dqdimacs.gz", "wt") as fp:
            fp.write(dqdimacs.dumps(f))
        return {
            "path": f"{name}.dqdimacs.gz",
            "expected": expected,
            "problem_key": problem_key,
            "tags": ["collatz", variant, params["step"]],
            "params": params,
        }

    by_variant: dict[str, list[dict]] = {}
    for enc in ("unrolled", "succinct", "tonly"):
        m = by_variant.setdefault(enc, [])
        for sv in step_variants:
            for n, k in _GRID[enc]:
                name = f"collatz_{enc}_{sv}_n{n:02d}_k{k:02d}"
                f = (
                    _compile_eqfob(eqfob_unrolled(n, k, sv))
                    if enc == "unrolled"
                    else _DIRECT[enc](n, k, sv)
                )
                e = emit(
                    enc,
                    name,
                    f,
                    expected=known_expected(enc, sv, n, k),
                    problem_key=f"collatz:{sv}:{n}",
                    params={"N": n, "K": k, "encoding": enc, "step": sv},
                )
                if e:
                    m.append(e)

    m = by_variant.setdefault("inductive", [])
    for sv in step_variants:
        for n, m_init in GRID_INDINV:
            name = f"collatz_indinv_{sv}_n{n:02d}_m{m_init:02d}"
            f = encode_indinv(collatz_transition(n, sv), source=name)
            e = emit(
                "inductive",
                name,
                f,
                expected="unknown",
                problem_key=f"collatz:{sv}:{n}",
                params={"N": n, "M": m_init, "encoding": "indinv", "step": sv},
            )
            if e:
                m.append(e)

    for variant, mf in by_variant.items():
        (base / variant / "manifest.json").write_text(json.dumps(mf, indent=2))
        print(f"{variant}: {len(mf)} instances")
    if skipped:
        print(f"skipped {len(skipped)} (>{VAR_CAP} vars)")


if __name__ == "__main__":
    main()
