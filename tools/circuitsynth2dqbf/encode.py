"""Minimal-circuit synthesis → DQBF.

Encodes "∃ a straight-line program of k gates over the full binary
basis B₂ computing `spec` for all inputs" as a DQBF. SAT means a
circuit of that size exists; UNSAT means none does (a lower bound).

Prefix shape:
  - universals       x[1..n]                — the inputs
  - existentials ∅   sa,sb,op,so,ladder     — circuit topology
  - existentials {x} a,b,v,spec-aux         — per-input gate values

Each gate's operation is encoded by its 4 truth-table bits, so the
basis is all 16 two-input Boolean functions (Kojevnikov–Kulikov–
Yaroslavtsev, SAT'09).  The depth variant arranges k = d·w gates in d
layers of width w; gate (l,·) may only read inputs and layers < l.

References: Kojevnikov, Kulikov, Yaroslavtsev, "Finding Efficient
Circuits Using SAT-Solvers", SAT 2009; Knuth, TAOCP Vol. 4A §7.1.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.formula import Formula, make_formula
from tools.circuitsynth2dqbf.spec_functions import Spec


@dataclass
class _Builder:
    """Incremental DQDIMACS builder."""

    universals: list[int] = field(default_factory=list)
    deps: dict[int, frozenset[int]] = field(default_factory=dict)
    clauses: list[list[int]] = field(default_factory=list)
    _next: int = 1

    def fresh_u(self) -> int:
        v = self._next
        self._next += 1
        self.universals.append(v)
        return v

    def fresh_e(self, dep: frozenset[int]) -> int:
        v = self._next
        self._next += 1
        self.deps[v] = dep
        return v

    def add(self, *lits: int) -> None:
        self.clauses.append(list(lits))

    def equiv(self, a: int, b: int) -> None:
        self.add(-a, b)
        self.add(a, -b)

    def gate_and(self, a: int, b: int, dep: frozenset[int]) -> int:
        o = self.fresh_e(dep)
        self.add(-o, a)
        self.add(-o, b)
        self.add(o, -a, -b)
        return o

    def gate_xor(self, a: int, b: int, dep: frozenset[int]) -> int:
        o = self.fresh_e(dep)
        self.add(-o, a, b)
        self.add(-o, -a, -b)
        self.add(o, -a, b)
        self.add(o, a, -b)
        return o

    def gate_or(self, a: int, b: int, dep: frozenset[int]) -> int:
        o = self.fresh_e(dep)
        self.add(o, -a)
        self.add(o, -b)
        self.add(-o, a, b)
        return o

    def exactly_one(self, lits: list[int], dep: frozenset[int]) -> None:
        """At-least-one + AMO. Pairwise AMO for tiny pools (no aux vars,
        so brute-force semantics stay tractable in tests); ladder/
        sequential AMO above that (linear clause count)."""
        self.add(*lits)
        if len(lits) <= 5:
            for i in range(len(lits)):
                for j in range(i + 1, len(lits)):
                    self.add(-lits[i], -lits[j])
            return
        prev = lits[0]
        for s in lits[1:]:
            r = self.fresh_e(dep)
            self.add(-s, -prev)  # s → ¬prev (AMO)
            self.add(-prev, r)  # r = prev ∨ s
            self.add(-s, r)
            self.add(prev, s, -r)
            prev = r

    def formula(self, comments: list[str]) -> Formula:
        return make_formula(
            universals=self.universals,
            dependencies=self.deps,
            clauses=self.clauses,
            comments=comments,
        )


def _spec_clauses(b: _Builder, spec: Spec, x: list[int], xdep: frozenset[int]) -> list[int]:
    """Tseitin the reference function; return one literal per output."""
    name = spec.name.rstrip("0123456789")
    if name in ("and", "or", "xor"):
        gate = {"and": b.gate_and, "or": b.gate_or, "xor": b.gate_xor}[name]
        acc = x[0]
        for xi in x[1:]:
            acc = gate(acc, xi, xdep)
        return [acc]
    if name == "eq":
        n = len(x) // 2
        xn = [-b.gate_xor(x[i], x[n + i], xdep) for i in range(n)]
        acc = xn[0]
        for xi in xn[1:]:
            acc = b.gate_and(acc, xi, xdep)
        return [acc]
    if name == "feistel":
        n = len(x) // 2
        L, R = x[:n], x[n:]
        fout = list(R)
        for i in range(n):
            fi = b.gate_and(R[i], R[(i + 1) % n], xdep)
            fout.append(b.gate_xor(L[i], fi, xdep))
        return fout
    if name == "inc":
        n = len(x)
        c: int | None = None
        out: list[int] = []
        for i in range(n):
            if c is None:
                out.append(-x[i])
                c = x[i]
            else:
                out.append(b.gate_xor(x[i], c, xdep))
                c = b.gate_and(x[i], c, xdep)
        assert c is not None
        out.append(c)
        return out
    if name == "lt":
        n = len(x) // 2
        A, B = x[:n], x[n:]
        bw: int | None = None
        for i in range(n):
            nlt = b.gate_and(-A[i], B[i], xdep)
            if bw is None:
                bw = nlt
            else:
                eq = -b.gate_xor(A[i], B[i], xdep)
                bw = b.gate_or(nlt, b.gate_and(eq, bw, xdep), xdep)
        assert bw is not None
        return [bw]
    if name == "add":
        n = len(x) // 2
        A, B = x[:n], x[n:]
        c2: int | None = None
        out2: list[int] = []
        for i in range(n):
            if c2 is None:
                out2.append(b.gate_xor(A[i], B[i], xdep))
                c2 = b.gate_and(A[i], B[i], xdep)
            else:
                t = b.gate_xor(A[i], B[i], xdep)
                out2.append(b.gate_xor(t, c2, xdep))
                c2 = b.gate_or(
                    b.gate_and(A[i], B[i], xdep), b.gate_and(t, c2, xdep), xdep
                )
        assert c2 is not None
        out2.append(c2)
        return out2
    # Generic fallback: truth-table (only when small).
    if spec.n_inputs > 10:
        raise ValueError(
            f"spec {spec.name}: n_inputs={spec.n_inputs} too large for "
            f"truth-table fallback and no structural builder"
        )
    outs = [b.fresh_e(xdep) for _ in range(spec.n_outputs)]
    for row in range(1 << spec.n_inputs):
        inbits = [(row >> j) & 1 == 1 for j in range(spec.n_inputs)]
        vals = spec.eval(inbits)
        guard = [-x[j] if inbits[j] else x[j] for j in range(spec.n_inputs)]
        for o, vv in enumerate(vals):
            b.add(*guard, outs[o] if vv else -outs[o])
    return outs


def _wire_mux(
    b: _Builder, sel: list[int], pool: list[int], target: int
) -> None:
    """sel[j] → (target ↔ pool[j]) for each j."""
    for s, w in zip(sel, pool, strict=True):
        b.add(-s, -target, w)
        b.add(-s, target, -w)


def _gate_semantics(b: _Builder, op: list[int], a: int, bb: int, v: int) -> None:
    """v ↔ op[2·a + b] for the 4 truth-table bits in `op`."""
    for ai in (0, 1):
        for bi in (0, 1):
            tt = op[2 * ai + bi]
            la = a if ai else -a
            lb = bb if bi else -bb
            b.add(-la, -lb, -tt, v)
            b.add(-la, -lb, tt, -v)


def encode_gates(spec: Spec, k: int) -> Formula:
    """∃ an SLP of k B₂-gates computing `spec` on all inputs."""
    b = _Builder()
    x = [b.fresh_u() for _ in range(spec.n_inputs)]
    xdep = frozenset(x)
    cdep: frozenset[int] = frozenset()

    pool: list[int] = list(x)  # wires available so far
    v: list[int] = []
    for _ in range(k):
        sa = [b.fresh_e(cdep) for _ in pool]
        sb = [b.fresh_e(cdep) for _ in pool]
        op = [b.fresh_e(cdep) for _ in range(4)]
        ai = b.fresh_e(xdep)
        bi = b.fresh_e(xdep)
        vi = b.fresh_e(xdep)
        b.exactly_one(sa, cdep)
        b.exactly_one(sb, cdep)
        _wire_mux(b, sa, pool, ai)
        _wire_mux(b, sb, pool, bi)
        _gate_semantics(b, op, ai, bi, vi)
        v.append(vi)
        pool = pool + [vi]

    spec_out = _spec_clauses(b, spec, x, xdep)
    for o in range(spec.n_outputs):
        so = [b.fresh_e(cdep) for _ in pool]
        b.exactly_one(so, cdep)
        _wire_mux(b, so, pool, spec_out[o])

    return b.formula(
        comments=[
            f"circuit_synth_gates spec={spec.name} k={k}",
            f"n_inputs={spec.n_inputs} n_outputs={spec.n_outputs}",
        ]
    )


def encode_depth(spec: Spec, depth: int, width: int) -> Formula:
    """∃ a depth-`depth` circuit (`width` gates per layer) computing `spec`."""
    b = _Builder()
    x = [b.fresh_u() for _ in range(spec.n_inputs)]
    xdep = frozenset(x)
    cdep: frozenset[int] = frozenset()

    layers: list[list[int]] = [list(x)]
    for _ in range(depth):
        avail = [w for layer in layers for w in layer]
        cur: list[int] = []
        for _ in range(width):
            sa = [b.fresh_e(cdep) for _ in avail]
            sb = [b.fresh_e(cdep) for _ in avail]
            op = [b.fresh_e(cdep) for _ in range(4)]
            ai = b.fresh_e(xdep)
            bi = b.fresh_e(xdep)
            vi = b.fresh_e(xdep)
            b.exactly_one(sa, cdep)
            b.exactly_one(sb, cdep)
            _wire_mux(b, sa, avail, ai)
            _wire_mux(b, sb, avail, bi)
            _gate_semantics(b, op, ai, bi, vi)
            cur.append(vi)
        layers.append(cur)

    pool = [w for layer in layers for w in layer]
    spec_out = _spec_clauses(b, spec, x, xdep)
    for o in range(spec.n_outputs):
        so = [b.fresh_e(cdep) for _ in pool]
        b.exactly_one(so, cdep)
        _wire_mux(b, so, pool, spec_out[o])

    return b.formula(
        comments=[
            f"circuit_synth_depth spec={spec.name} depth={depth} width={width}",
            f"n_inputs={spec.n_inputs} n_outputs={spec.n_outputs}",
        ]
    )
