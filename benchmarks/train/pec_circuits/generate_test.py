from benchmarks.train.pec_circuits.generate import (
    _classify_gates,
    _gate_cone,
    _mutate,
    _rank_by_input_cone,
)
from tools.bmc2dqbf.circuits import circuit_alu_add, circuit_mutex
from tools.pec2dqbf.aiger_seq import parse_seq_aag


def test_classify_disjoint() -> None:
    aag, _ = circuit_alu_add(4)
    circ = parse_seq_aag(aag)
    bad_only, trans_only = _classify_gates(circ)
    assert set(bad_only) & set(trans_only) == set()
    assert bad_only and trans_only


def test_rank_monotone() -> None:
    aag, _ = circuit_alu_add(4)
    circ = parse_seq_aag(aag)
    _, trans_only = _classify_gates(circ)
    ranked = _rank_by_input_cone(circ, trans_only)
    src = set(circ.inputs)
    leaves = src | {lat.lit for lat in circ.latches}
    gm = circ.gate_map()

    def csize(g: int) -> int:
        a, b = gm[g]
        return len((circ.cone_inputs(a, leaves) | circ.cone_inputs(b, leaves)) & src)

    sizes = [csize(g) for g in ranked]
    assert sizes == sorted(sizes, reverse=True)


def test_mutate_only_target() -> None:
    aag, _ = circuit_mutex(4)
    circ = parse_seq_aag(aag)
    target = circ.gates[0][0]
    m = _mutate(circ, target)
    for (g0, a0, b0), (g1, a1, b1) in zip(circ.gates, m.gates, strict=True):
        assert g0 == g1 and b0 == b1
        if g0 == target:
            assert a1 == a0 ^ 1
        else:
            assert a1 == a0


def test_gate_cone_subset_of_gates() -> None:
    aag, _ = circuit_alu_add(2)
    circ = parse_seq_aag(aag)
    cone = _gate_cone(circ, circ.bad)
    assert cone <= {g for g, _, _ in circ.gates}
