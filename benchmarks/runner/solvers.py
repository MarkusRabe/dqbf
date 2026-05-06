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
    domain: str = "dqbf"  # "dqbf" | "qbf" | "hwmc" | "syntcomp"


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
        "frust": Solver(
            name="frust",
            cmd=[
                str(ROOT / "provers/frust/target/release/frust"),
                "{file}",
                "--timeout",
                "{timeout}",
                "--cert",
                "{certdir}/{stem}.aag",
                "--proof",
                "{certdir}/{stem}.frp",
            ],
            certs={"sat": "{certdir}/{stem}.aag", "unsat": "{certdir}/{stem}.frp"},
            available=_exists(str(ROOT / "provers/frust/target/release/frust")),
        ),
        **{
            f"frust-{v}": Solver(
                name=f"frust-{v}",
                cmd=[
                    f"/tmp/frust-{v}",
                    "{file}",
                    "--timeout",
                    "{timeout}",
                    "--cert",
                    "{certdir}/{stem}.aag",
                    "--proof",
                    "{certdir}/{stem}.frp",
                ],
                certs={"sat": "{certdir}/{stem}.aag", "unsat": "{certdir}/{stem}.frp"},
                available=_exists(f"/tmp/frust-{v}"),
            )
            for v in ("v1.20", "v2.0")
        },
        "cadet": Solver(
            name="cadet",
            cmd=[cadet, "-c", "{certdir}/{stem}.aag", "{file}"],
            certs={"sat": "{certdir}/{stem}.aag"},
            available=_exists(cadet),
            domain="qbf",
            input_format="qdimacs",
        ),
        "caqe": Solver(
            name="caqe",
            cmd=[caqe, "{file}"],
            certs={},
            available=_exists(caqe),
            domain="qbf",
            input_format="qdimacs",
        ),
        "rareqs": Solver(
            name="rareqs",
            cmd=[rareqs, "{file}"],
            certs={},
            available=_exists(rareqs),
            domain="qbf",
            input_format="qdimacs",
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
                "read {file}; bmc3 -F {kp1} -T {timeout}",
            ],
            certs={},
            available=_exists("berkeley-abc") or _exists("abc"),
            input_format="aag",
            domain="hwmc",
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
            domain="hwmc",
        ),
        "avy": Solver(
            name="avy",
            cmd=[str(ROOT / "third_party/avy/build/avy/src/avy"), "{file}"],
            certs={},
            available=_exists(str(ROOT / "third_party/avy/build/avy/src/avy")),
            input_format="aag",
            domain="hwmc",
        ),
        # --- Reactive synthesis (consume TLSF, not DQDIMACS) ---
        "strix": Solver(
            name="strix",
            cmd=[
                sys.executable,
                str(ROOT / "scripts/run_strix_tlsf.py"),
                "{file}",
            ],
            certs={},
            available=_exists(str(ROOT / "third_party/strix/strix")),
            input_format="tlsf",
            domain="syntcomp",
        ),
        "bosy": Solver(
            name="bosy",
            cmd=[str(ROOT / "third_party/bosy/bosy"), "{file}"],
            certs={},
            available=_exists(str(ROOT / "third_party/bosy/bosy")),
            input_format="tlsf",
            domain="syntcomp",
        ),
    }
