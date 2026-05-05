"""Tests for the result cache."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from benchmarks.runner.cache import instance_hash, key, load, solver_hash, store


@pytest.fixture
def tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "cache"
    monkeypatch.setattr("benchmarks.runner.cache.CACHE_DIR", d)
    return d


def test_solver_hash_differs_on_binary_change(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.write_bytes(b"\x7fELF...v1")
    b.write_bytes(b"\x7fELF...v2")
    assert solver_hash([str(a), "{file}"]) != solver_hash([str(b), "{file}"])
    a.write_bytes(b"\x7fELF...v2")
    assert solver_hash([str(a), "{file}"]) == solver_hash([str(b), "{file}"])


def test_instance_hash_ignores_gzip_envelope(tmp_path: Path) -> None:
    raw = b"p cnf 3 2\n1 -2 0\n2 3 0\n"
    p1 = tmp_path / "x.dqdimacs"
    p1.write_bytes(raw)
    p2 = tmp_path / "x.dqdimacs.gz"
    p2.write_bytes(gzip.compress(raw, mtime=0))
    p3 = tmp_path / "y.dqdimacs.gz"
    p3.write_bytes(gzip.compress(raw, mtime=123))
    assert instance_hash(p1) == instance_hash(p2) == instance_hash(p3)


def test_roundtrip(tmp_cache: Path) -> None:
    k = key("aaa", "bbb", 10.0)
    assert load(k) is None
    row = {"solver": "frust", "got": "sat", "wall_s": 1.2, "cert_status": "valid"}
    store(k, row)
    got = load(k)
    assert got == row
    # different timeout → different key
    assert load(key("aaa", "bbb", 5.0)) is None
