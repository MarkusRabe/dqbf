"""EQFOB abstract syntax.

Declarations are frozen; expression nodes carry a mutable `.width` slot
filled by typecheck (−1 = not yet typed; bool-typed nodes get width 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

WidthExpr = int | str  # literal width or param/sort name


# ---- declarations ---------------------------------------------------------


@dataclass(frozen=True)
class Param:
    name: str
    value: int


@dataclass(frozen=True)
class Sort:
    name: str
    width: WidthExpr


@dataclass(frozen=True)
class FunDecl:
    name: str
    arg_sorts: tuple[WidthExpr, ...]
    ret_sort: WidthExpr


class VarKind(Enum):
    EXISTS = "exists"
    FORALL = "forall"


@dataclass(frozen=True)
class VarDecl:
    name: str
    sort: WidthExpr
    kind: VarKind


# ---- expressions ---------------------------------------------------------


@dataclass
class Expr:
    width: int = field(default=-1, init=False)


@dataclass
class BVConst(Expr):
    value: int
    declared_width: WidthExpr | None = None  # bv literal like 3:bv[4]; None = infer


@dataclass
class BVVar(Expr):
    name: str


@dataclass
class FunApp(Expr):
    name: str
    args: tuple[Expr, ...]


BV_UNOPS = {"neg", "bvnot"}
BV_BINOPS = {
    "add",
    "sub",
    "mul",
    "and",
    "or",
    "xor",
    "shl",
    "lshr",
    "ashr",
    "concat",
}
CMP_OPS = {"eq", "ne", "ult", "ule", "ugt", "uge", "slt", "sle", "sgt", "sge"}
BOOL_BINOPS = {"land", "lor", "impl", "iff"}


@dataclass
class BVUnOp(Expr):
    op: str
    arg: Expr


@dataclass
class BVBinOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class Extract(Expr):
    hi: int
    lo: int
    arg: Expr


@dataclass
class Extend(Expr):
    kind: Literal["zext", "sext"]
    by: int
    arg: Expr


@dataclass
class Ite(Expr):
    cond: Expr
    then: Expr
    els: Expr


@dataclass
class Cmp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class BoolNot(Expr):
    arg: Expr


@dataclass
class BoolBinOp(Expr):
    op: str
    left: Expr
    right: Expr


# ---- problem -------------------------------------------------------------


@dataclass
class Problem:
    params: list[Param] = field(default_factory=list)
    sorts: list[Sort] = field(default_factory=list)
    funs: list[FunDecl] = field(default_factory=list)
    vars: list[VarDecl] = field(default_factory=list)
    constraints: list[Expr] = field(default_factory=list)
