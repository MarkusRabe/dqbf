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


def _exists(p: str) -> bool:
    return Path(p).exists() or shutil.which(p) is not None


def registry() -> dict[str, Solver]:
    cadet = str(ROOT / "third_party/cadet/cadet")
    caqe = str(ROOT / "third_party/caqe/target/release/caqe")
    rareqs = str(ROOT / "third_party/rareqs/rareqs-1.1/rareqs")
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
    }
