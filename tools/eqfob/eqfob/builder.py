"""Programmatic EQFOB construction.

Thin convenience layer over ast/typecheck/bitblast — see CLAUDE.md for
the intended user-facing API.
"""

from __future__ import annotations

from core.formula import Formula
from tools.eqfob.eqfob.ast import (
    BVVar,
    Expr,
    FunApp,
    FunDecl,
    Param,
    Sort,
    VarDecl,
    VarKind,
    WidthExpr,
)
from tools.eqfob.eqfob.ast import (
    Problem as _Problem,
)
from tools.eqfob.eqfob.bitblast import bitblast
from tools.eqfob.eqfob.typecheck import check


class _FunHandle:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, *args: Expr) -> FunApp:
        return FunApp(name=self.name, args=tuple(args))


class Problem:
    def __init__(self) -> None:
        self._p = _Problem()

    def param(self, name: str, value: int) -> str:
        self._p.params.append(Param(name=name, value=value))
        return name

    def sort(self, name: str, width: WidthExpr) -> str:
        self._p.sorts.append(Sort(name=name, width=width))
        return name

    def fun(self, name: str, args: list[WidthExpr], ret: WidthExpr) -> _FunHandle:
        self._p.funs.append(FunDecl(name=name, arg_sorts=tuple(args), ret_sort=ret))
        return _FunHandle(name)

    def forall(self, name: str, sort: WidthExpr) -> BVVar:
        self._p.vars.append(VarDecl(name=name, sort=sort, kind=VarKind.FORALL))
        return BVVar(name=name)

    def exists(self, name: str, sort: WidthExpr) -> BVVar:
        self._p.vars.append(VarDecl(name=name, sort=sort, kind=VarKind.EXISTS))
        return BVVar(name=name)

    def add(self, constraint: Expr) -> None:
        self._p.constraints.append(constraint)

    def to_dqbf(self, overrides: dict[str, int] | None = None) -> Formula:
        return bitblast(check(self._p, overrides=overrides))
