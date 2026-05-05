"""Validate every cbmc-style circuit's expected reachability.

For each (family, bug) at tiny n, build the AIGER, encode as *unrolled*
BMC at a bound deep enough for the bug to manifest, and SAT-solve. The
unrolled encoding with safe=False is propositional (no universals), so a
plain SAT call is the ground-truth oracle. Then check the succinct
encoding agrees on that same instance via core.semantics.
"""

from __future__ import annotations

import pytest

from core.semantics import is_true
from tools.bmc2dqbf.encode import encode, encode_succinct
from tools.cbmc2dqbf.circuits import BUG_DEPTH, REGISTRY_CBMC, expected_at
from tools.pec2dqbf.aiger_seq import parse_seq_aag
from tools.verify.sat import solve_cnf

# Per-family (n, k) chosen so the bug is reachable within k and the
# brute-force semantics check on the succinct form stays under budget.
PARAMS: dict[str, tuple[int, int]] = {
    "popcount": (3, 6),
    "parity": (3, 6),
    "bitrev": (3, 6),
    "mul_shiftadd": (2, 5),
    "divmod": (3, 6),
    "gcd_sub": (3, 4),
    "stream_min": (3, 3),
    "sat_ctr": (3, 3),
    "clz": (3, 7),
    "fib": (3, 3),
    "token_bucket": (2, 6),
    "onehot_rt": (3, 4),
}


def _unrolled_sat(name: str, n: int, bug: bool, k: int) -> bool:
    aag, _, _ = REGISTRY_CBMC[name](n, bug)
    f = encode(parse_seq_aag(aag), k=k, safe=False)
    assert not f.universals
    sat, _ = solve_cnf(f.n_vars, [list(c) for c in f.clauses])
    assert sat is not None, "no SAT backend"
    return sat


@pytest.mark.parametrize("name", sorted(REGISTRY_CBMC))
@pytest.mark.parametrize("bug", [False, True])
def test_unrolled_reachability_matches_expected(name: str, bug: bool) -> None:
    n, k = PARAMS[name]
    got = "sat" if _unrolled_sat(name, n, bug, k) else "unsat"
    want = expected_at(name, n, bug, k)
    assert got == want, f"{name} bug={bug} n={n} k={k}: expected {want}, got {got}"


@pytest.mark.parametrize("name", sorted(REGISTRY_CBMC))
def test_bug_depth_reachable(name: str) -> None:
    """At k=BUG_DEPTH(n) the bug must be reachable (sufficient bound)."""
    n, _ = PARAMS[name]
    d = BUG_DEPTH[name](n)
    assert _unrolled_sat(name, n, bug=True, k=d), (
        f"{name} n={n}: bug not reachable at k={d}, depth too low"
    )


@pytest.mark.parametrize("name", sorted(REGISTRY_CBMC))
@pytest.mark.parametrize("bug", [False, True])
def test_succinct_agrees_with_unrolled(name: str, bug: bool) -> None:
    n, k = PARAMS[name]
    aag, _, _ = REGISTRY_CBMC[name](n, bug)
    seq = parse_seq_aag(aag)
    sat_unroll = _unrolled_sat(name, n, bug, k)
    f_succ = encode_succinct(seq, k=k)
    if len(f_succ.universals) > 8:
        pytest.skip(f"|U|={len(f_succ.universals)} too large for brute-force oracle")
    verdict = is_true(f_succ)
    assert verdict is not None, "semantics oracle hit budget"
    assert verdict == sat_unroll, (
        f"{name} bug={bug}: succinct={verdict} vs unrolled={sat_unroll}"
    )
