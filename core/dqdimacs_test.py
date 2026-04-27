from pathlib import Path

import pytest

from core import dqdimacs
from core.formula import make_formula

TINY = """\
c example
p cnf 4 4
a 1 2 0
d 3 1 0
d 4 2 0
3 4 0
-3 -4 0
1 -3 0
2 -4 0
"""


def test_parse_tiny() -> None:
    f = dqdimacs.parse(TINY)
    assert f.n_vars == 4
    assert f.universals == (1, 2)
    assert f.dependencies == {3: frozenset({1}), 4: frozenset({2})}
    assert len(f.clauses) == 4
    assert frozenset({3, 4}) in f.clauses


def test_roundtrip() -> None:
    f = dqdimacs.parse(TINY)
    s = dqdimacs.dumps(f)
    g = dqdimacs.parse(s)
    assert g.universals == f.universals
    assert g.dependencies == f.dependencies
    assert set(g.clauses) == set(f.clauses)


def test_e_line_depends_on_preceding_universals() -> None:
    f = dqdimacs.parse("p cnf 4 0\na 1 0\ne 3 0\na 2 0\ne 4 0\n")
    assert f.dependencies[3] == {1}
    assert f.dependencies[4] == {1, 2}


def test_dump_canonical() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1], 4: [2]}, clauses=[[-3, 4]])
    s = dqdimacs.dumps(f)
    assert "a 1 2 0\n" in s
    assert "d 3 1 0\n" in s
    assert "-3 4 0\n" in s


BENCH = Path(__file__).parent.parent / "benchmarks" / "holdout" / "dqbf" / "qbfeval" / "dqbf"


@pytest.mark.skipif(not BENCH.exists(), reason="qbfeval benchmarks not present")
def test_load_qbfeval_sample() -> None:
    paths = sorted(BENCH.glob("*.dqdimacs"))[:5] + sorted(BENCH.glob("*.dqdimacs.gz"))[:2]
    assert paths, "no benchmark files found"
    for p in paths:
        f = dqdimacs.load(p)
        assert f.n_vars > 0
        assert len(f.clauses) > 0
        g = dqdimacs.parse(dqdimacs.dumps(f))
        assert set(g.clauses) == set(f.clauses)
        assert g.dependencies == f.dependencies
