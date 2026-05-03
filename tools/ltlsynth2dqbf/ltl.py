"""Tiny LTL parser → AST.

Grammar (loosely; precedence high→low):
  atom := IDENT | true | false | ( expr )
  unary := (! | G | F | X) unary | atom
  binU := unary ( (U|W|R) unary )*
  and  := binU ( && binU )*
  or   := and ( || and )*
  impl := or ( -> or )*       (right-assoc)
  iff  := impl ( <-> impl )*

AST nodes are tuples: ('atom', name) | ('true',) | ('false',) |
('not', a) | ('and', a, b) | ('or', a, b) | ('impl', a, b) |
('iff', a, b) | ('G', a) | ('F', a) | ('X', a) | ('U', a, b) |
('W', a, b) | ('R', a, b).
"""

from __future__ import annotations

import re

Node = tuple

_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<LP>\()|(?P<RP>\))|"
    r"(?P<IFF><->)|(?P<IMPL>->)|(?P<AND>&&)|(?P<OR>\|\|)|(?P<NOT>!)|"
    r"(?P<KW>\b(?:true|false|G|F|X|U|W|R)\b)|"
    r"(?P<ID>[A-Za-z_][A-Za-z0-9_]*)"
    r")"
)


class LtlParseError(ValueError):
    pass


def parse(s: str) -> Node:
    toks = list(_tokenize(s))
    pos = [0]

    def peek() -> tuple[str, str] | None:
        return toks[pos[0]] if pos[0] < len(toks) else None

    def eat(kind: str | None = None) -> tuple[str, str]:
        t = peek()
        if t is None:
            raise LtlParseError("unexpected end of input")
        if kind and t[0] != kind:
            raise LtlParseError(f"expected {kind}, got {t}")
        pos[0] += 1
        return t

    def atom() -> Node:
        t = peek()
        if t is None:
            raise LtlParseError("expected atom")
        if t[0] == "LP":
            eat()
            e = iff()
            eat("RP")
            return e
        if t[0] == "KW" and t[1] in ("true", "false"):
            eat()
            return (t[1],)
        if t[0] == "ID":
            eat()
            return ("atom", t[1])
        raise LtlParseError(f"unexpected token {t}")

    def unary() -> Node:
        t = peek()
        if t and t[0] == "NOT":
            eat()
            return ("not", unary())
        if t and t[0] == "KW" and t[1] in ("G", "F", "X"):
            eat()
            return (t[1], unary())
        return atom()

    def binu() -> Node:
        a = unary()
        while (t := peek()) and t[0] == "KW" and t[1] in ("U", "W", "R"):
            eat()
            b = unary()
            a = (t[1], a, b)
        return a

    def conj() -> Node:
        a = binu()
        while (t := peek()) and t[0] == "AND":
            eat()
            a = ("and", a, binu())
        return a

    def disj() -> Node:
        a = conj()
        while (t := peek()) and t[0] == "OR":
            eat()
            a = ("or", a, conj())
        return a

    def impl() -> Node:
        a = disj()
        if (t := peek()) and t[0] == "IMPL":
            eat()
            return ("impl", a, impl())
        return a

    def iff() -> Node:
        a = impl()
        while (t := peek()) and t[0] == "IFF":
            eat()
            a = ("iff", a, impl())
        return a

    e = iff()
    if pos[0] != len(toks):
        raise LtlParseError(f"trailing tokens: {toks[pos[0] :]}")
    return e


def _tokenize(s: str):
    i = 0
    while i < len(s):
        m = _TOKEN.match(s, i)
        if not m:
            if s[i:].strip():
                raise LtlParseError(f"bad char at {i}: {s[i : i + 20]!r}")
            return
        i = m.end()
        for k, v in m.groupdict().items():
            if v is not None:
                yield (k, v)
                break


def atoms_of(n: Node) -> set[str]:
    if n[0] == "atom":
        return {n[1]}
    out: set[str] = set()
    for c in n[1:]:
        if isinstance(c, tuple):
            out |= atoms_of(c)
    return out


def is_temporal_free(n: Node) -> bool:
    if n[0] in ("G", "F", "X", "U", "W", "R"):
        return False
    return all(is_temporal_free(c) for c in n[1:] if isinstance(c, tuple))
