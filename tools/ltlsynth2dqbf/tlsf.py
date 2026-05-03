"""Minimal TLSF (basic format) parser.

Handles the un-parameterized subset: INFO, MAIN { INPUTS / OUTPUTS /
INITIALLY / PRESET / REQUIRE / ASSERT / ASSUME / ASSUMPTIONS /
GUARANTEE / GUARANTEES }, plus a single-level GLOBAL { PARAMETERS } with
integer literals and array signal expansion `r[n] → r_0..r_{n-1}` and
big-op `&&[l <= i < u] body` / `||[...]` expansion.

Anything else (DEFINITIONS, nested ops, non-integer params) raises
TlsfNotSupported with a clear message — the runner can then mark the
instance n/a and synthesis tools (which read TLSF natively) still run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class TlsfNotSupported(ValueError):
    pass


@dataclass
class TlsfSpec:
    title: str = ""
    semantics: str = "mealy"
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    initially: list[str] = field(default_factory=list)
    preset: list[str] = field(default_factory=list)
    require: list[str] = field(default_factory=list)
    assert_: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    guarantees: list[str] = field(default_factory=list)
    status: str | None = None  # from `//STATUS : realizable` comment

    def ltl_formula(self) -> str:
        """Combine sections into a single LTL formula per the TLSF spec
        semantics: (∧ INITIALLY ∧ G(∧ PRESET) ∧ ∧ ASSUME) →
                   (∧ REQUIRE ∧ G(∧ ASSERT) ∧ ∧ GUARANTEE)."""
        a_parts = list(self.initially)
        if self.preset:
            a_parts.append(f"G ({_conj(self.preset)})")
        a_parts += self.assumptions
        g_parts = list(self.require)
        if self.assert_:
            g_parts.append(f"G ({_conj(self.assert_)})")
        g_parts += self.guarantees
        a = _conj(a_parts) if a_parts else "true"
        g = _conj(g_parts) if g_parts else "true"
        if a == "true":
            return g
        return f"({a}) -> ({g})"


def _conj(xs: list[str]) -> str:
    return " && ".join(f"({x})" for x in xs) if xs else "true"


_SECTION_KEYS = {
    "INPUTS": "inputs",
    "OUTPUTS": "outputs",
    "INITIALLY": "initially",
    "PRESET": "preset",
    "REQUIRE": "require",
    "REQUIRES": "require",
    "ASSERT": "assert_",
    "INVARIANT": "assert_",
    "INVARIANTS": "assert_",
    "ASSUME": "assumptions",
    "ASSUMPTIONS": "assumptions",
    "GUARANTEE": "guarantees",
    "GUARANTEES": "guarantees",
}


def parse(text: str) -> TlsfSpec:
    spec = TlsfSpec()
    # status from trailing comment
    m = re.search(r"//\s*STATUS\s*:\s*(\w+)", text, re.IGNORECASE)
    if m:
        spec.status = m.group(1).lower()
    # strip line comments
    text = re.sub(r"//[^\n]*", "", text)
    pos = 0
    params: dict[str, int] = {}
    while pos < len(text):
        m = re.match(r"\s*(\w+)\s*\{", text[pos:])
        if not m:
            if text[pos:].strip():
                raise TlsfNotSupported(
                    f"unexpected content at offset {pos}: {text[pos : pos + 40]!r}"
                )
            break
        block_name = m.group(1).upper()
        body, pos = _read_block(text, pos + m.end() - 1)
        if block_name == "INFO":
            tm = re.search(r'TITLE\s*:\s*"([^"]*)"', body)
            if tm:
                spec.title = tm.group(1)
            sm = re.search(r"SEMANTICS\s*:\s*(\w+)", body)
            if sm:
                spec.semantics = sm.group(1).lower()
        elif block_name == "GLOBAL":
            params = _parse_global(body)
        elif block_name == "MAIN":
            _parse_main(body, spec, params)
        else:
            raise TlsfNotSupported(f"top-level block {block_name!r}")
    return spec


def _read_block(text: str, open_brace_pos: int) -> tuple[str, int]:
    assert text[open_brace_pos] == "{"
    depth = 0
    i = open_brace_pos
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_pos + 1 : i], i + 1
        i += 1
    raise TlsfNotSupported("unbalanced braces")


def _parse_global(body: str) -> dict[str, int]:
    params: dict[str, int] = {}
    pos = 0
    while pos < len(body):
        m = re.match(r"\s*(\w+)\s*\{", body[pos:])
        if not m:
            if body[pos:].strip():
                raise TlsfNotSupported(f"GLOBAL: unexpected {body[pos : pos + 40]!r}")
            break
        name = m.group(1).upper()
        inner, pos = _read_block(body, pos + m.end() - 1)
        if name == "PARAMETERS":
            for pm in re.finditer(r"(\w+)\s*=\s*(\d+)\s*;", inner):
                params[pm.group(1)] = int(pm.group(2))
        elif name == "DEFINITIONS":
            raise TlsfNotSupported("GLOBAL.DEFINITIONS not supported (need syfco)")
        else:
            raise TlsfNotSupported(f"GLOBAL.{name} not supported")
    return params


def _parse_main(body: str, spec: TlsfSpec, params: dict[str, int]) -> None:
    pos = 0
    while pos < len(body):
        m = re.match(r"\s*(\w+)\s*\{", body[pos:])
        if not m:
            if body[pos:].strip():
                raise TlsfNotSupported(f"MAIN: unexpected {body[pos : pos + 40]!r}")
            break
        sec = m.group(1).upper()
        inner, pos = _read_block(body, pos + m.end() - 1)
        if sec not in _SECTION_KEYS:
            raise TlsfNotSupported(f"MAIN.{sec} not supported")
        attr = _SECTION_KEYS[sec]
        items = _split_semis(inner)
        if attr in ("inputs", "outputs"):
            sigs: list[str] = []
            for it in items:
                sigs.extend(_expand_signal(it, params))
            getattr(spec, attr).extend(sigs)
        else:
            for it in items:
                getattr(spec, attr).append(_expand_bigops(it, params))


def _split_semis(s: str) -> list[str]:
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            t = "".join(cur).strip()
            if t:
                out.append(t)
            cur = []
        else:
            cur.append(ch)
    t = "".join(cur).strip()
    if t:
        out.append(t)
    return out


def _expand_signal(decl: str, params: dict[str, int]) -> list[str]:
    decl = decl.strip()
    m = re.fullmatch(r"(\w+)\s*\[\s*(\w+)\s*\]", decl)
    if m:
        name, sz = m.group(1), m.group(2)
        n = params.get(sz, int(sz) if sz.isdigit() else None)
        if n is None:
            raise TlsfNotSupported(f"array size {sz!r} not a known parameter")
        return [f"{name}_{i}" for i in range(n)]
    if not re.fullmatch(r"\w+", decl):
        raise TlsfNotSupported(f"signal decl {decl!r}")
    return [decl]


_BIGOP = re.compile(r"(&&|\|\|)\s*\[\s*(\w+)\s*(<=|<)\s*(\w+)\s*(<=|<)\s*(\w+)\s*\]\s*")


def _expand_bigops(expr: str, params: dict[str, int]) -> str:
    while True:
        m = _BIGOP.search(expr)
        if not m:
            break
        op, lo, lop, var, rop, hi = m.groups()
        lo_v = params.get(lo, int(lo) if lo.isdigit() else None)
        hi_v = params.get(hi, int(hi) if hi.isdigit() else None)
        if lo_v is None or hi_v is None:
            raise TlsfNotSupported(f"big-op bounds {lo}/{hi} not resolvable")
        if lop == "<":
            lo_v += 1
        if rop == "<=":
            hi_v += 1
        body, end = _read_term_after(expr, m.end())
        parts = []
        for i in range(lo_v, hi_v):
            sub = re.sub(rf"\b{re.escape(var)}\b", str(i), body)
            sub = re.sub(r"(\w+)\s*\[\s*(\d+)\s*\]", r"\1_\2", sub)
            parts.append(f"({sub})")
        joined = (" && " if op == "&&" else " || ").join(parts) or (
            "true" if op == "&&" else "false"
        )
        expr = expr[: m.start()] + f"({joined})" + expr[end:]
    # any remaining x[k] indexing
    expr = re.sub(r"(\w+)\s*\[\s*(\d+)\s*\]", r"\1_\2", expr)
    return expr


def _read_term_after(expr: str, start: int) -> tuple[str, int]:
    """Read one balanced term (parenthesized or up to the next binary op)."""
    i = start
    while i < len(expr) and expr[i].isspace():
        i += 1
    if i < len(expr) and expr[i] == "(":
        depth = 0
        j = i
        while j < len(expr):
            if expr[j] == "(":
                depth += 1
            elif expr[j] == ")":
                depth -= 1
                if depth == 0:
                    return expr[i + 1 : j], j + 1
            j += 1
        raise TlsfNotSupported("unbalanced () in big-op body")
    # bare term up to end or `;`
    j = i
    while j < len(expr) and expr[j] not in ";":
        j += 1
    return expr[i:j], j
