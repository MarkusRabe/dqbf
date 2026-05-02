from core.aiger import parse_aag, skolem_to_aag
from core.formula import make_formula


def test_aag_writer_produces_valid_header() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1], 4: [2]}, clauses=[[-1, 3]])
    sk: dict[int, dict[tuple[bool, ...], bool]] = {
        3: {(False,): False, (True,): True},
        4: {(False,): True, (True,): False},
    }
    aag = skolem_to_aag(f, sk)
    assert aag.startswith("aag ")
    lines = aag.strip().splitlines()
    hdr = lines[0].split()
    assert hdr[0] == "aag" and hdr[3] == "0"  # combinational
    assert any(ln.startswith("o0 e3") for ln in lines)


def test_aag_roundtrip() -> None:
    f = make_formula(universals=[1, 2], dependencies={3: [1], 4: [2]}, clauses=[])
    sk: dict[int, dict[tuple[bool, ...], bool]] = {
        3: {(False,): False, (True,): True},
        4: {(False,): True, (True,): False},
    }
    aig = parse_aag(skolem_to_aag(f, sk))
    out3 = aig.output_by_name("e3")
    assert out3 is not None
    assert aig.output_by_name("e4") is not None
    assert aig.cone_inputs(out3) <= set(aig.inputs)
