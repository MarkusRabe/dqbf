"""Incomplete-circuit BMC / PEC → DQBF. See CLAUDE.md."""

from __future__ import annotations

from pathlib import Path

from core.formula import Formula


def encode(aiger_path: str | Path, blackboxes: list[str], k: int) -> Formula:
    raise NotImplementedError(
        "bmc2dqbf: each black-box output bit → existential with deps = its input bits; "
        "k-step unrolling shares the same dep set across frames (Gitina et al. ICCD'13)."
    )
