import pytest

from tools.bmc2dqbf.circuits_v2 import REGISTRY_V2
from tools.pec2dqbf.aiger_seq import parse_seq_aag


@pytest.mark.parametrize("name", sorted(REGISTRY_V2))
@pytest.mark.parametrize("n", [4, 8])
def test_v2_circuit_parses(name: str, n: int) -> None:
    aag, comment = REGISTRY_V2[name](n)
    seq = parse_seq_aag(aag)
    assert len(seq.latches) > 0
    assert isinstance(seq.bad, int)
    assert comment
