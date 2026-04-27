from pathlib import Path

from tools.eqfob.eqfob.ast import BVBinOp, Cmp, FunApp, VarKind
from tools.eqfob.eqfob.parse import parse

EX = Path(__file__).resolve().parents[1] / "examples"


def test_parse_add_gt() -> None:
    p = parse((EX / "add_gt.eqfob").read_text())
    assert [pa.name for pa in p.params] == ["A", "B"]
    assert {f.name for f in p.funs} == {"f", "g"}
    assert [(v.name, v.kind) for v in p.vars] == [("z", VarKind.EXISTS), ("x", VarKind.FORALL)]
    assert len(p.constraints) == 1
    c = p.constraints[0]
    assert isinstance(c, Cmp) and c.op == "ugt"
    assert isinstance(c.left, BVBinOp) and c.left.op == "add"


def test_parse_dep_cycle() -> None:
    p = parse((EX / "dep_cycle.eqfob").read_text())
    assert {f.name for f in p.funs} == {"y1", "y2", "y3"}
    c = p.constraints[0]
    assert isinstance(c, Cmp) and c.op == "eq"
    assert isinstance(c.left, BVBinOp) and c.left.op == "xor"


def test_parse_inline_ops() -> None:
    p = parse(
        """
        param N = 4
        forall a : bv[N]
        forall b : bv[N]
        (a + b) == (b + a)
        a & b == b & a
        !(a < b) <-> (a >= b)
        """
    )
    assert len(p.constraints) == 3
    c0 = p.constraints[0]
    assert isinstance(c0, Cmp) and c0.op == "eq"
    assert isinstance(c0.left, BVBinOp) and c0.left.op == "add"


def test_parse_call_multi_arg() -> None:
    p = parse(
        """
        fun h : bv[2], bv[2] -> bv[1]
        forall x : bv[2]
        h(x, x) == 0
        """
    )
    fa = p.constraints[0].left
    assert isinstance(fa, FunApp) and fa.name == "h" and len(fa.args) == 2
