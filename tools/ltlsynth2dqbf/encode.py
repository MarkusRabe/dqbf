"""LTL bounded synthesis → DQBF. See CLAUDE.md."""

from __future__ import annotations

from core.formula import Formula


def encode(tlsf_text: str, n_states: int) -> Formula:
    raise NotImplementedError(
        "ltlsynth2dqbf: ∀ source,target,input. ∃ δ(s,i),λ(s,i). co-Büchi-bounded run constraint "
        "(Faymonville-Finkbeiner-Tentrup TACAS'17)."
    )
