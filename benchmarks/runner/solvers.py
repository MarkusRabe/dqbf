"""Solver registry: how to invoke each backend, where its cert lands."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Solver:
    name: str
    cmd: list[str]  # {file} {timeout} {certdir} placeholders
    certs: dict[str, str]  # result -> path template, e.g. {"sat": "{certdir}/{stem}.aag"}
    available: bool
    input_format: str = "dqdimacs"  # "dqdimacs" | "aag" | "tlsf"


def _exists(p: str) -> bool:
    return Path(p).exists() or shutil.which(p) is not None


def registry() -> dict[str, Solver]:
    cadet = str(ROOT / "third_party/cadet/cadet")
    caqe = str(ROOT / "third_party/caqe/target/release/caqe")
    rareqs = str(ROOT / "third_party/rareqs/rareqs-1.1/rareqs")
    dqbdd = str(ROOT / "third_party/dqbdd/Release/src/dqbdd")
    pedant = str(ROOT / "third_party/pedant/build/src/pedant")
    hqs = str(ROOT / "third_party/hqs/HQS/build/src/hqs/hqs2")
    return {
        "forkres": Solver(
            name="forkres",
            cmd=[
                sys.executable,
                "-m",
                "provers.forkres.cli",
                "{file}",
                "--timeout",
                "{timeout}",
                "--cert",
                "{certdir}/{stem}.skolem.json",
                "--proof",
                "{certdir}/{stem}.frp",
            ],
            certs={
                "sat": "{certdir}/{stem}.skolem.json.aag",
                "unsat": "{certdir}/{stem}.frp",
            },
            available=True,
        ),
        "cadet": Solver(
            name="cadet",
            cmd=[cadet, "-c", "{certdir}/{stem}.aag", "{file}"],
            certs={"sat": "{certdir}/{stem}.aag"},
            available=_exists(cadet),
        ),
        "caqe": Solver(
            name="caqe",
            cmd=[caqe, "{file}"],
            certs={},
            available=_exists(caqe),
        ),
        "rareqs": Solver(
            name="rareqs",
            cmd=[rareqs, "{file}"],
            certs={},
            available=_exists(rareqs),
        ),
        "dqbdd": Solver(
            name="dqbdd",
            cmd=[dqbdd, "{file}"],
            certs={},
            available=_exists(dqbdd),
        ),
        "pedant": Solver(
            name="pedant",
            cmd=[pedant, "{file}", "--aag", "{certdir}/{stem}.aag"],
            certs={"sat": "{certdir}/{stem}.aag"},
            available=_exists(pedant),
        ),
        "hqs": Solver(
            name="hqs",
            cmd=[hqs, "{file}"],
            certs={},
            available=_exists(hqs),
        ),
        # --- HW model checkers (consume AIGER, not DQDIMACS) ---
        "abc-bmc": Solver(
            name="abc-bmc",
            cmd=[
                shutil.which("berkeley-abc") or shutil.which("abc") or "abc",
                "-q",
                "read {file}; bmc3 -F 1000 -T {timeout}",
            ],
            certs={},
            available=_exists("berkeley-abc") or _exists("abc"),
            input_format="aag",
        ),
        "abc-pdr": Solver(
            name="abc-pdr",
            cmd=[
                shutil.which("berkeley-abc") or shutil.which("abc") or "abc",
                "-q",
                "read {file}; pdr -T {timeout}",
            ],
            certs={},
            available=_exists("berkeley-abc") or _exists("abc"),
            input_format="aag",
        ),
        "avy": Solver(
            name="avy",
            cmd=[str(ROOT / "third_party/avy/build/avy/src/avy"), "{file}"],
            certs={},
            available=_exists(str(ROOT / "third_party/avy/build/avy/src/avy")),
            input_format="aag",
        ),
    }
