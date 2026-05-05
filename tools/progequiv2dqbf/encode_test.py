"""progequiv2dqbf tests.

The encoder reifies every guard (EQ/STEP/at-pc/halted) as a Tseitin
existential, so even the W=A=0, R=1, K=2 instance has ~27 existentials.
`core.semantics.is_true` enumerates the full Skolem-function product
(∏ 2^(2^|dep|)), which is ≳10^16 here — out of reach. Semantic checks
are therefore marked `xfail` until either the encoder inlines guards
as clause prefixes or a smarter oracle is added; structural checks and
DQDIMACS roundtrip are exercised unconditionally.
"""

from __future__ import annotations

import pytest

from core import dqdimacs
from core.semantics import is_true
from tools.progequiv2dqbf.encode import Config, encode_bounded, encode_coupling
from tools.progequiv2dqbf.isa import parse

REG_ONLY = Config(word_bits=1, addr_bits=0, n_regs=1, bound=2, out_reg=0)
WITH_MEM = Config(word_bits=1, addr_bits=1, n_regs=2, bound=2, out_reg=0)


def test_isa_parse() -> None:
    p = parse("MOV r0 1\nADD r0 r0 r0\nHALT\n", name="t")
    assert [i.op for i in p.instrs] == ["MOV", "ADD", "HALT"]
    assert p.instrs[0].args == (0, 1)
    with pytest.raises(ValueError):
        parse("MOV r0 1\n")  # no HALT


def test_mem_prefix_shape() -> None:
    """Memory existentials must have dep = {t, a} (and {t', a'} for the
    primed copy) — that *is* the encoding's point."""
    p = parse("MOV r1 0\nLOAD r0 r1\nHALT\n", "P")
    f = encode_bounded(p, p, WITH_MEM)
    t, tp, a, ap = f.universals  # m=A=1
    dep_sets = set(f.dependencies.values())
    assert frozenset({t, a}) in dep_sets  # memP(t,a)
    assert frozenset({tp, ap}) in dep_sets  # memP'(t',a')
    assert frozenset({t}) in dep_sets  # regP(t), pcP(t)
    # Incomparable deps ⇒ genuine DQBF, not a QBF prefix.
    assert not frozenset({t, a}) <= frozenset({tp, ap})
    assert not frozenset({tp, ap}) <= frozenset({t, a})


def test_dqdimacs_roundtrip() -> None:
    p = parse("MOV r1 0\nLOAD r0 r1\nSTORE r1 r0\nHALT\n", "P")
    q = parse("MOV r1 0\nLOAD r0 r1\nHALT\n", "Q")
    f = encode_bounded(p, q, Config(word_bits=2, addr_bits=2, n_regs=2, bound=4))
    text = dqdimacs.dumps(f)
    g = dqdimacs.parse(text)
    assert g.n_vars == f.n_vars
    assert set(g.universals) == set(f.universals)
    assert g.dependencies == f.dependencies
    assert len(g.clauses) == len(f.clauses)


@pytest.mark.xfail(reason="is_true enumerates full Skolem space; ≥27 existentials", run=False)
def test_reg_only_identical_sat() -> None:
    src = "MOV r0 1\nHALT\n"
    f = encode_bounded(parse(src, "P"), parse(src, "Q"), REG_ONLY)
    assert is_true(f) is True


@pytest.mark.xfail(reason="is_true enumerates full Skolem space; ≥27 existentials", run=False)
def test_reg_only_differ_unsat() -> None:
    p = parse("MOV r0 0\nHALT\n", "P")
    q = parse("MOV r0 1\nHALT\n", "Q")
    assert is_true(encode_bounded(p, q, REG_ONLY)) is False


def test_coupling_is_stub() -> None:
    p = parse("HALT\n", "P")
    with pytest.raises(NotImplementedError):
        encode_coupling(p, p, REG_ONLY)
