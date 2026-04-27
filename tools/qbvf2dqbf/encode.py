"""SMT-LIB2 BV/UFBV → DQBF. See CLAUDE.md for the encoding plan."""

from __future__ import annotations

from core.formula import Formula


def encode(smtlib_text: str) -> Formula:
    raise NotImplementedError(
        "qbvf2dqbf: bit-blast under prefix; UF symbols → existentials with arg-bit deps. "
        "Implement via the EQFOB bit-blaster once merged."
    )
