"""Expose each cbmc-style algorithm as a sequential-AIGER transition system.

The `SeqAig` packs (I, T, P, state, input) in standard AIGER form:
inputs = primary inputs per step, latches = state with reset (= I) and
next-function (= T), first output = bad signal (= ¬P). Any encoder that
consumes `SeqAig` (unrolled BMC, succinct step-counter BMC, inductive-
invariant search) can use these directly.
"""

from __future__ import annotations

from tools.cbmc2dqbf.circuits import REGISTRY_CBMC, expected_at
from tools.pec2dqbf.aiger_seq import SeqAig, parse_seq_aag


def seq_aig_for(name: str, n: int, bug: bool) -> tuple[SeqAig, str]:
    """Build the transition system for `name` at bit-width `n`.

    Returns (seq_aig, comment). For the expected BMC verdict at a given
    bound, use `tools.cbmc2dqbf.circuits.expected_at(name, n, bug, k)`.
    """
    aag, _, comment = REGISTRY_CBMC[name](n, bug)
    return parse_seq_aag(aag), comment


__all__ = ["seq_aig_for", "expected_at", "families"]


def families() -> list[str]:
    return sorted(REGISTRY_CBMC)
