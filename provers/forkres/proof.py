"""Prover-side proof emission. The trace *format* lives in
`core.proof_trace`; this module is a thin re-export plus the prover's
own (non-authoritative) replay used during search for sanity checks.
The independent checker is `tools/verify/unsat.py`.
"""

from __future__ import annotations

from core.proof_trace import Proof, Step, load, save
from tools.verify.unsat import verify_proof as replay

__all__ = ["Proof", "Step", "load", "save", "replay"]
