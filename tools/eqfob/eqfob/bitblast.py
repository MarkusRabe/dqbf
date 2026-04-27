"""Bit-blast a TypedProblem to a core.Formula (DQBF in CNF).

Variable allocation order:
  1. forall-var bits (DQBF universals)
  2. exists-var bits (DQBF existentials, deps = preceding universals)
  3. per FunApp call site: ret-width fresh existentials, deps = universals
     reachable from the argument expressions
  4. Tseitin gate auxiliaries (existentials, deps = union of input deps)

For multiple call sites of the same function, Ackermann congruence
constraints are added.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.formula import Formula
from tools.eqfob.eqfob.ast import (
    BoolBinOp,
    BoolNot,
    BVBinOp,
    BVConst,
    BVUnOp,
    BVVar,
    Cmp,
    Expr,
    Extend,
    Extract,
    FunApp,
    Ite,
    VarKind,
)
from tools.eqfob.eqfob.typecheck import TypedProblem

Bits = list[int]  # LSB-first list of literals
Deps = frozenset[int]


@dataclass
class _Blaster:
    tp: TypedProblem
    next_var: int = 0
    universals: list[int] = field(default_factory=list)
    deps: dict[int, Deps] = field(default_factory=dict)
    clauses: list[frozenset[int]] = field(default_factory=list)
    var_bits: dict[str, Bits] = field(default_factory=dict)
    var_deps: dict[str, Deps] = field(default_factory=dict)
    calls: dict[str, list[tuple[list[Bits], Bits, Deps]]] = field(default_factory=dict)
    const_true: int = 0

    # ---- allocation ----
    def fresh_universal(self) -> int:
        self.next_var += 1
        v = self.next_var
        self.universals.append(v)
        return v

    def fresh_exist(self, dep: Deps) -> int:
        self.next_var += 1
        v = self.next_var
        self.deps[v] = dep
        return v

    def true_lit(self) -> int:
        if self.const_true == 0:
            t = self.fresh_exist(frozenset())
            self.const_true = t
            self.clauses.append(frozenset({t}))
        return self.const_true

    def lit_dep(self, lit: int) -> Deps:
        v = abs(lit)
        if v in self.deps:
            return self.deps[v]
        return frozenset({v})  # universal

    # ---- gates (Tseitin) ----
    def g_and(self, a: int, b: int, dep: Deps) -> int:
        o = self.fresh_exist(dep)
        self.clauses += [
            frozenset({-o, a}),
            frozenset({-o, b}),
            frozenset({o, -a, -b}),
        ]
        return o

    def g_or(self, a: int, b: int, dep: Deps) -> int:
        o = self.fresh_exist(dep)
        self.clauses += [
            frozenset({o, -a}),
            frozenset({o, -b}),
            frozenset({-o, a, b}),
        ]
        return o

    def g_xor(self, a: int, b: int, dep: Deps) -> int:
        o = self.fresh_exist(dep)
        self.clauses += [
            frozenset({-o, a, b}),
            frozenset({-o, -a, -b}),
            frozenset({o, -a, b}),
            frozenset({o, a, -b}),
        ]
        return o

    def g_mux(self, c: int, t: int, e: int, dep: Deps) -> int:
        o = self.fresh_exist(dep)
        self.clauses += [
            frozenset({-c, -t, o}),
            frozenset({-c, t, -o}),
            frozenset({c, -e, o}),
            frozenset({c, e, -o}),
        ]
        return o

    def g_eq(self, a: int, b: int, dep: Deps) -> int:
        return -self.g_xor(a, b, dep)

    def conjoin(self, lits: list[int], dep: Deps) -> int:
        if not lits:
            return self.true_lit()
        acc = lits[0]
        for x in lits[1:]:
            acc = self.g_and(acc, x, dep)
        return acc

    # ---- BV ops ----
    def bv_bitwise(self, op: str, a: Bits, b: Bits, dep: Deps) -> Bits:
        g = {"and": self.g_and, "or": self.g_or, "xor": self.g_xor}[op]
        return [g(x, y, dep) for x, y in zip(a, b, strict=True)]

    def bv_add(self, a: Bits, b: Bits, dep: Deps) -> Bits:
        out: Bits = []
        carry = -self.true_lit()
        for x, y in zip(a, b, strict=True):
            s1 = self.g_xor(x, y, dep)
            s = self.g_xor(s1, carry, dep)
            c1 = self.g_and(x, y, dep)
            c2 = self.g_and(s1, carry, dep)
            carry = self.g_or(c1, c2, dep)
            out.append(s)
        return out

    def bv_neg(self, a: Bits, dep: Deps) -> Bits:
        inv = [-x for x in a]
        one = self.bv_const(1, len(a))
        return self.bv_add(inv, one, dep)

    def bv_sub(self, a: Bits, b: Bits, dep: Deps) -> Bits:
        return self.bv_add(a, self.bv_neg(b, dep), dep)

    def bv_mul(self, a: Bits, b: Bits, dep: Deps) -> Bits:
        n = len(a)
        acc = self.bv_const(0, n)
        for i, bi in enumerate(b):
            partial = [-self.true_lit()] * i + [self.g_and(bi, aj, dep) for aj in a[: n - i]]
            acc = self.bv_add(acc, partial, dep)
        return acc

    def bv_const(self, v: int, w: int) -> Bits:
        t = self.true_lit()
        return [t if (v >> i) & 1 else -t for i in range(w)]

    def bv_shift(self, op: str, a: Bits, amt: int, dep: Deps) -> Bits:
        n = len(a)
        f = -self.true_lit()
        if op == "shl":
            return ([f] * amt + a)[:n]
        if op == "lshr":
            return (a + [f] * amt)[amt : amt + n]
        if op == "ashr":
            return (a + [a[-1]] * amt)[amt : amt + n]
        raise NotImplementedError(op)

    def bv_cmp(self, op: str, a: Bits, b: Bits, dep: Deps) -> int:
        if op == "eq":
            return self.conjoin([self.g_eq(x, y, dep) for x, y in zip(a, b, strict=True)], dep)
        if op == "ne":
            return -self.bv_cmp("eq", a, b, dep)
        if op == "ult":
            # a < b iff borrow-out of a - b is 1; compute via ripple
            lt = -self.true_lit()
            for x, y in zip(a, b, strict=True):
                eq = self.g_eq(x, y, dep)
                lt = self.g_mux(eq, lt, self.g_and(-x, y, dep), dep)
            return lt
        if op == "ule":
            return -self.bv_cmp("ult", b, a, dep)
        if op == "ugt":
            return self.bv_cmp("ult", b, a, dep)
        if op == "uge":
            return -self.bv_cmp("ult", a, b, dep)
        if op in ("slt", "sle", "sgt", "sge"):
            af = a[:-1] + [-a[-1]]
            bf = b[:-1] + [-b[-1]]
            return self.bv_cmp("u" + op[1:], af, bf, dep)
        raise NotImplementedError(op)

    # ---- expression dispatch ----
    def blast(self, e: Expr) -> tuple[Bits, Deps]:  # noqa: C901
        if isinstance(e, BVConst):
            return self.bv_const(e.value, e.width), frozenset()
        if isinstance(e, BVVar):
            return list(self.var_bits[e.name]), self.var_deps[e.name]
        if isinstance(e, FunApp):
            arg_bits: list[Bits] = []
            dep: Deps = frozenset()
            for a in e.args:
                b, d = self.blast(a)
                arg_bits.append(b)
                dep |= d
            outs = [self.fresh_exist(dep) for _ in range(e.width)]
            self.calls.setdefault(e.name, []).append((arg_bits, outs, dep))
            return outs, dep
        if isinstance(e, BVUnOp):
            b, d = self.blast(e.arg)
            if e.op == "bvnot":
                return [-x for x in b], d
            if e.op == "neg":
                return self.bv_neg(b, d), d
            raise NotImplementedError(e.op)
        if isinstance(e, BVBinOp):
            lb, ld = self.blast(e.left)
            if e.op in ("shl", "lshr", "ashr"):
                if not isinstance(e.right, BVConst):
                    raise NotImplementedError("variable shift amount")
                return self.bv_shift(e.op, lb, e.right.value, ld), ld
            rb, rd = self.blast(e.right)
            d = ld | rd
            if e.op in ("and", "or", "xor"):
                return self.bv_bitwise(e.op, lb, rb, d), d
            if e.op == "add":
                return self.bv_add(lb, rb, d), d
            if e.op == "sub":
                return self.bv_sub(lb, rb, d), d
            if e.op == "mul":
                return self.bv_mul(lb, rb, d), d
            if e.op == "concat":
                return rb + lb, d  # left is high bits
            raise NotImplementedError(e.op)
        if isinstance(e, Extract):
            b, d = self.blast(e.arg)
            return b[e.lo : e.hi + 1], d
        if isinstance(e, Extend):
            b, d = self.blast(e.arg)
            fill = b[-1] if e.kind == "sext" else -self.true_lit()
            return b + [fill] * e.by, d
        if isinstance(e, Ite):
            cb, cd = self.blast(e.cond)
            tb, td = self.blast(e.then)
            eb, ed = self.blast(e.els)
            d = cd | td | ed
            return [self.g_mux(cb[0], t, el, d) for t, el in zip(tb, eb, strict=True)], d
        if isinstance(e, Cmp):
            lb, ld = self.blast(e.left)
            rb, rd = self.blast(e.right)
            d = ld | rd
            return [self.bv_cmp(e.op, lb, rb, d)], d
        if isinstance(e, BoolNot):
            b, d = self.blast(e.arg)
            return [-b[0]], d
        if isinstance(e, BoolBinOp):
            lb, ld = self.blast(e.left)
            rb, rd = self.blast(e.right)
            d = ld | rd
            a, b2 = lb[0], rb[0]
            if e.op == "land":
                return [self.g_and(a, b2, d)], d
            if e.op == "lor":
                return [self.g_or(a, b2, d)], d
            if e.op == "iff":
                return [self.g_eq(a, b2, d)], d
            if e.op == "impl":
                return [self.g_or(-a, b2, d)], d
            raise NotImplementedError(e.op)
        raise NotImplementedError(type(e).__name__)

    # ---- Ackermann ----
    def add_ackermann(self) -> None:
        for _name, sites in self.calls.items():
            for i in range(len(sites)):
                for j in range(i + 1, len(sites)):
                    ai, oi, di = sites[i]
                    aj, oj, dj = sites[j]
                    d = di | dj
                    eqs = []
                    for ba, bb in zip(ai, aj, strict=True):
                        for x, y in zip(ba, bb, strict=True):
                            eqs.append(self.g_eq(x, y, d))
                    args_eq = self.conjoin(eqs, d) if eqs else self.true_lit()
                    for x, y in zip(oi, oj, strict=True):
                        out_eq = self.g_eq(x, y, d)
                        impl = self.g_or(-args_eq, out_eq, d)
                        self.clauses.append(frozenset({impl}))


def bitblast(tp: TypedProblem) -> Formula:
    bl = _Blaster(tp=tp)
    seen_universals: list[int] = []
    for name, w, kind in tp.vars:
        if kind is VarKind.FORALL:
            bits = [bl.fresh_universal() for _ in range(w)]
            bl.var_bits[name] = bits
            bl.var_deps[name] = frozenset(bits)
            seen_universals += bits
        else:
            dep = frozenset(seen_universals)
            bits = [bl.fresh_exist(dep) for _ in range(w)]
            bl.var_bits[name] = bits
            bl.var_deps[name] = dep

    for c in tp.constraints:
        bits, _d = bl.blast(c)
        bl.clauses.append(frozenset({bits[0]}))

    bl.add_ackermann()

    return Formula(
        n_vars=bl.next_var,
        universals=tuple(bl.universals),
        dependencies=bl.deps,
        clauses=tuple(bl.clauses),
        comments=("generated by eqfob",),
    )
