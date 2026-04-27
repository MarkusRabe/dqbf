"""EQFOB textual syntax → AST (Lark)."""

from __future__ import annotations

from lark import Lark, Transformer, v_args

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
    FunDecl,
    Ite,
    Param,
    Problem,
    Sort,
    VarDecl,
    VarKind,
    WidthExpr,
)

GRAMMAR = r"""
start: decl*

decl: "param" NAME "=" INT                  -> param
    | "sort"  NAME "=" sort                 -> sortdecl
    | "fun"   NAME ":" sortlist "->" sort   -> fundecl
    | "exists" NAME ":" sort                -> existsdecl
    | "forall" NAME ":" sort                -> foralldecl
    | expr                                  -> constraint

sortlist: sort ("," sort)*
sort: "bv" "[" widthexpr "]"  -> bvsort
    | NAME                    -> namedsort
widthexpr: INT | NAME

?expr: iff
?iff:  imp ("<->" imp)*
?imp:  lor ("->" lor)*
?lor:  land ("||" land)*
?land: cmp ("&&" cmp)*
?cmp:  bor (CMPOP bor)?
?bor:  bxor ("|" bxor)*
?bxor: band ("^" band)*
?band: shift ("&" shift)*
?shift: add (SHIFTOP add)*
?add:  mul (ADDOP mul)*
?mul:  unary ("*" unary)*
?unary: "!" unary    -> lnot
      | "~" unary    -> bvnot
      | "-" unary    -> neg
      | postfix
?postfix: atom
        | "extract" "[" INT ":" INT "]" "(" expr ")" -> extract
        | "zext" "[" INT "]" "(" expr ")"            -> zext
        | "sext" "[" INT "]" "(" expr ")"            -> sext
        | "ite" "(" expr "," expr "," expr ")"       -> ite
?atom: INT                        -> const
     | NAME "(" arglist? ")"      -> call
     | NAME                       -> varref
     | "(" expr ")"

arglist: expr ("," expr)*

CMPOP: "==" | "!=" | "<=" | ">=" | "<" | ">"
SHIFTOP: ">>>" | ">>" | "<<"
ADDOP: "+" | "-"

COMMENT: /--[^\n]*/
%import common.CNAME -> NAME
%import common.INT
%import common.WS
%ignore WS
%ignore COMMENT
"""

_CMP = {"==": "eq", "!=": "ne", "<": "ult", "<=": "ule", ">": "ugt", ">=": "uge"}
_SHIFT = {"<<": "shl", ">>": "ashr", ">>>": "lshr"}
_ADD = {"+": "add", "-": "sub"}


def _chain_bv(op: str, items: list[Expr]) -> Expr:
    e = items[0]
    for r in items[1:]:
        e = BVBinOp(op=op, left=e, right=r)
    return e


def _chain_bool(op: str, items: list[Expr]) -> Expr:
    e = items[0]
    for r in items[1:]:
        e = BoolBinOp(op=op, left=e, right=r)
    return e


@v_args(inline=False)
class _Builder(Transformer):
    def start(self, decls):
        p = Problem()
        for kind, val in decls:
            getattr(p, kind).append(val)
        return p

    def param(self, ch):
        return ("params", Param(name=str(ch[0]), value=int(ch[1])))

    def sortdecl(self, ch):
        return ("sorts", Sort(name=str(ch[0]), width=ch[1]))

    def fundecl(self, ch):
        name, args, ret = str(ch[0]), ch[1], ch[2]
        return ("funs", FunDecl(name=name, arg_sorts=tuple(args), ret_sort=ret))

    def existsdecl(self, ch):
        return ("vars", VarDecl(name=str(ch[0]), sort=ch[1], kind=VarKind.EXISTS))

    def foralldecl(self, ch):
        return ("vars", VarDecl(name=str(ch[0]), sort=ch[1], kind=VarKind.FORALL))

    def constraint(self, ch):
        return ("constraints", ch[0])

    def sortlist(self, ch):
        return list(ch)

    def bvsort(self, ch) -> WidthExpr:
        return ch[0]

    def namedsort(self, ch) -> WidthExpr:
        return str(ch[0])

    def widthexpr(self, ch) -> WidthExpr:
        t = ch[0]
        return int(t) if t.type == "INT" else str(t)

    # ---- expressions ----
    def iff(self, ch):
        return _chain_bool("iff", list(ch))

    def imp(self, ch):
        return _chain_bool("impl", list(ch))

    def lor(self, ch):
        return _chain_bool("lor", list(ch))

    def land(self, ch):
        return _chain_bool("land", list(ch))

    def cmp(self, ch):
        if len(ch) == 1:
            return ch[0]
        left, op, right = ch
        return Cmp(op=_CMP[str(op)], left=left, right=right)

    def bor(self, ch):
        return _chain_bv("or", list(ch))

    def bxor(self, ch):
        return _chain_bv("xor", list(ch))

    def band(self, ch):
        return _chain_bv("and", list(ch))

    def shift(self, ch):
        items = list(ch)
        e = items[0]
        i = 1
        while i < len(items):
            op = _SHIFT[str(items[i])]
            e = BVBinOp(op=op, left=e, right=items[i + 1])
            i += 2
        return e

    def add(self, ch):
        items = list(ch)
        e = items[0]
        i = 1
        while i < len(items):
            op = _ADD[str(items[i])]
            e = BVBinOp(op=op, left=e, right=items[i + 1])
            i += 2
        return e

    def mul(self, ch):
        return _chain_bv("mul", list(ch))

    def lnot(self, ch):
        return BoolNot(arg=ch[0])

    def bvnot(self, ch):
        return BVUnOp(op="bvnot", arg=ch[0])

    def neg(self, ch):
        return BVUnOp(op="neg", arg=ch[0])

    def extract(self, ch):
        return Extract(hi=int(ch[0]), lo=int(ch[1]), arg=ch[2])

    def zext(self, ch):
        return Extend(kind="zext", by=int(ch[0]), arg=ch[1])

    def sext(self, ch):
        return Extend(kind="sext", by=int(ch[0]), arg=ch[1])

    def ite(self, ch):
        return Ite(cond=ch[0], then=ch[1], els=ch[2])

    def const(self, ch):
        return BVConst(value=int(ch[0]))

    def call(self, ch):
        name = str(ch[0])
        args = tuple(ch[1]) if len(ch) > 1 else ()
        return FunApp(name=name, args=args)

    def varref(self, ch):
        return BVVar(name=str(ch[0]))

    def arglist(self, ch):
        return list(ch)


_PARSER = Lark(GRAMMAR, parser="lalr", maybe_placeholders=False)


def parse(text: str) -> Problem:
    tree = _PARSER.parse(text)
    return _Builder().transform(tree)
