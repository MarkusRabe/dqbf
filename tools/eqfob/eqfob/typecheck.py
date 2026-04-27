"""Width inference and checking for EQFOB ASTs."""

from __future__ import annotations

from dataclasses import dataclass, field

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
    Problem,
    VarKind,
    WidthExpr,
)


class TypeError_(Exception):
    pass


@dataclass
class TypedProblem:
    params: dict[str, int]
    funs: dict[str, tuple[tuple[int, ...], int]]  # name -> (arg widths, ret width)
    vars: list[tuple[str, int, VarKind]]  # in declaration order
    constraints: list[Expr]  # width-annotated in place

    var_width: dict[str, int] = field(default_factory=dict)
    var_kind: dict[str, VarKind] = field(default_factory=dict)


def _resolve(w: WidthExpr, env: dict[str, int]) -> int:
    if isinstance(w, int):
        return w
    if w in env:
        return env[w]
    raise TypeError_(f"unknown width/sort/param '{w}'")


def check(p: Problem, overrides: dict[str, int] | None = None) -> TypedProblem:
    overrides = overrides or {}
    env: dict[str, int] = {}
    for pa in p.params:
        env[pa.name] = overrides.get(pa.name, pa.value)
    for s in p.sorts:
        env[s.name] = _resolve(s.width, env)

    funs: dict[str, tuple[tuple[int, ...], int]] = {}
    for fd in p.funs:
        funs[fd.name] = (
            tuple(_resolve(a, env) for a in fd.arg_sorts),
            _resolve(fd.ret_sort, env),
        )

    vars_: list[tuple[str, int, VarKind]] = []
    var_width: dict[str, int] = {}
    var_kind: dict[str, VarKind] = {}
    for vd in p.vars:
        w = _resolve(vd.sort, env)
        vars_.append((vd.name, w, vd.kind))
        var_width[vd.name] = w
        var_kind[vd.name] = vd.kind

    tp = TypedProblem(
        params=env,
        funs=funs,
        vars=vars_,
        constraints=p.constraints,
        var_width=var_width,
        var_kind=var_kind,
    )

    for c in p.constraints:
        w = _infer(c, tp)
        if w != 1:
            raise TypeError_(f"top-level constraint has width {w}, expected 1 (bool)")
    return tp


def _unify(a: Expr, b: Expr) -> int:
    if a.width == -1 and b.width == -1:
        raise TypeError_("cannot infer width: both operands untyped")
    if a.width == -1:
        a.width = b.width
    if b.width == -1:
        b.width = a.width
    if a.width != b.width:
        raise TypeError_(f"width mismatch: {a.width} vs {b.width}")
    return a.width


def _infer(e: Expr, tp: TypedProblem) -> int:  # noqa: C901
    if e.width != -1:
        return e.width
    if isinstance(e, BVConst):
        if e.declared_width is not None:
            e.width = _resolve(e.declared_width, tp.params)
        # else: leave -1 for parent to unify
        return e.width
    if isinstance(e, BVVar):
        if e.name not in tp.var_width:
            raise TypeError_(f"unknown variable '{e.name}'")
        e.width = tp.var_width[e.name]
        return e.width
    if isinstance(e, FunApp):
        if e.name not in tp.funs:
            raise TypeError_(f"unknown function '{e.name}'")
        arg_ws, ret_w = tp.funs[e.name]
        if len(e.args) != len(arg_ws):
            raise TypeError_(f"{e.name}: arity {len(arg_ws)}, got {len(e.args)}")
        for a, w in zip(e.args, arg_ws, strict=True):
            _infer(a, tp)
            if a.width == -1:
                a.width = w
            if a.width != w:
                raise TypeError_(f"{e.name}: arg width {a.width}, expected {w}")
        e.width = ret_w
        return ret_w
    if isinstance(e, BVUnOp):
        e.width = _infer(e.arg, tp)
        if e.width == -1:
            raise TypeError_(f"cannot infer width of {e.op} operand")
        return e.width
    if isinstance(e, BVBinOp):
        _infer(e.left, tp)
        _infer(e.right, tp)
        if e.op == "concat":
            if e.left.width == -1 or e.right.width == -1:
                raise TypeError_("concat operands need explicit widths")
            e.width = e.left.width + e.right.width
        elif e.op in ("shl", "lshr", "ashr"):
            if e.left.width == -1:
                raise TypeError_("shift LHS needs explicit width")
            e.width = e.left.width
        else:
            e.width = _unify(e.left, e.right)
        return e.width
    if isinstance(e, Extract):
        _infer(e.arg, tp)
        e.width = e.hi - e.lo + 1
        return e.width
    if isinstance(e, Extend):
        w = _infer(e.arg, tp)
        if w == -1:
            raise TypeError_("extend operand needs explicit width")
        e.width = w + e.by
        return e.width
    if isinstance(e, Ite):
        cw = _infer(e.cond, tp)
        if cw != 1:
            raise TypeError_(f"ite condition has width {cw}, expected 1")
        _infer(e.then, tp)
        _infer(e.els, tp)
        e.width = _unify(e.then, e.els)
        return e.width
    if isinstance(e, Cmp):
        _infer(e.left, tp)
        _infer(e.right, tp)
        _unify(e.left, e.right)
        e.width = 1
        return 1
    if isinstance(e, BoolNot):
        w = _infer(e.arg, tp)
        if w == -1:
            e.arg.width = 1
        elif w != 1:
            raise TypeError_(f"! operand has width {w}, expected 1")
        e.width = 1
        return 1
    if isinstance(e, BoolBinOp):
        for s in (e.left, e.right):
            w = _infer(s, tp)
            if w == -1:
                s.width = 1
            elif w != 1:
                raise TypeError_(f"{e.op} operand has width {w}, expected 1")
        e.width = 1
        return 1
    raise TypeError_(f"unhandled node {type(e).__name__}")
