"""Generate bitwidth-scaling EQFOB instances: one BV op, swept over width N.

Each instance is `∃f. ∀x[,y]. f(args) == expr(args)`, compiled to DQBF.
"""

from __future__ import annotations

from collections.abc import Iterator

OPS_UNARY = {"id": "x", "not": "~x", "inc": "x + 1"}
OPS_BINARY = {"add": "x + y", "and": "x & y", "or": "x | y", "xor": "x ^ y"}


def instances(widths: list[int]) -> Iterator[tuple[str, dict[str, int], str]]:
    for n in widths:
        for name, rhs in OPS_UNARY.items():
            yield f"{name}_n{n}", {"N": n}, _src_unary(rhs)
        for name, rhs in OPS_BINARY.items():
            yield f"{name}_n{n}", {"N": n}, _src_binary(rhs)


def _src_unary(rhs: str) -> str:
    return f"param N = 2\nfun f : bv[N] -> bv[N]\nforall x : bv[N]\nf(x) == {rhs}\n"


def _src_binary(rhs: str) -> str:
    return (
        "param N = 2\n"
        "fun f : bv[N], bv[N] -> bv[N]\n"
        "forall x : bv[N]\n"
        "forall y : bv[N]\n"
        f"f(x, y) == {rhs}\n"
    )


def main() -> None:
    import json

    manifest = []
    for name, params, _src in instances(widths=[2, 4, 8]):
        manifest.append({"name": name, "params": params, "expected": "sat"})
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
