"""Verify a fork-resolution refutation trace against a DQBF."""

from __future__ import annotations

from core.formula import Formula
from provers.forkres.proof import Proof, replay


def verify_proof(f: Formula, proof: Proof) -> bool:
    return replay(f, proof)
