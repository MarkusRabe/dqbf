"""Reverse the existential variable IDs of a DQDIMACS instance,
preserving the universals. Used to test that the solver doesn't
implicitly depend on the encoder's ID assignment order.

A solver that relies on `var-id encodes step order` will see a
performance regression on the reversed instance even though it's
semantically identical (just a renaming).

Usage:
    python -m scripts.revid INPUT.dqdimacs[.gz] OUTPUT.dqdimacs
    python -m scripts.revid --shuffle SEED INPUT OUTPUT  # random permutation
"""

from __future__ import annotations

import gzip
import random
import sys
from pathlib import Path


def remap(text: str, permute: dict[int, int]) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith(("c", "p", "a")):
            out.append(line)
            continue
        toks = line.split()
        if not toks:
            out.append(line)
            continue
        if toks[0] == "d":
            v = int(toks[1])
            rest = toks[2:]
            out.append(f"d {permute.get(v, v)} " + " ".join(rest))
            continue
        new = []
        for t in toks:
            try:
                x = int(t)
            except ValueError:
                new.append(t)
                continue
            v = abs(x)
            v2 = permute.get(v, v)
            new.append(str(v2 if x > 0 else -v2))
        out.append(" ".join(new))
    return "\n".join(out) + "\n"


def main() -> None:
    args = sys.argv[1:]
    shuffle_seed: int | None = None
    if args and args[0] == "--shuffle":
        shuffle_seed = int(args[1])
        args = args[2:]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    src, dst = Path(args[0]), Path(args[1])
    raw = src.read_bytes()
    if src.suffix == ".gz":
        raw = gzip.decompress(raw)
    text = raw.decode()
    # Existentials = vars in `d` lines.
    exs = []
    for line in text.splitlines():
        if line.startswith("d "):
            exs.append(int(line.split()[1]))
    targets = list(exs)
    if shuffle_seed is not None:
        rng = random.Random(shuffle_seed)
        rng.shuffle(targets)
    else:
        targets = list(reversed(targets))
    permute = dict(zip(exs, targets, strict=True))
    dst.write_text(remap(text, permute))
    print(f"{len(exs)} existentials remapped: {src} -> {dst}")


if __name__ == "__main__":
    main()
