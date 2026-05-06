"""Tests for _find_source token-subset / sibling-variant matching."""

from __future__ import annotations

from pathlib import Path

from benchmarks.runner.multi import _find_source


def _tree(root: Path, files: list[str]) -> None:
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")


def test_prefix_match_unchanged(tmp_path: Path) -> None:
    """alu_add_n4_k008 → alu_add_n4.aag (worked before; still works)."""
    _tree(tmp_path, [
        "unrolled/alu_add/alu_add_n4.aag",
        "unrolled/alu_add/alu_add_n8.aag",
        "unrolled/alu_add/alu_add_n4_k008.dqdimacs.gz",
    ])
    inst = tmp_path / "unrolled/alu_add/alu_add_n4_k008.dqdimacs.gz"
    got = _find_source(inst, ".aag")
    assert got is not None and got.name == "alu_add_n4.aag"


def test_token_subset_reordered_suffix(tmp_path: Path) -> None:
    """barrel_n4_k008_bug → barrel_n4_bug.aag (broken before)."""
    _tree(tmp_path, [
        "unrolled/barrel/barrel_n4_bug.aag",
        "unrolled/barrel/barrel_n4_safe.aag",
        "unrolled/barrel/barrel_n4_k008_bug.dqdimacs.gz",
        "unrolled/barrel/barrel_n4_k008_safe.dqdimacs.gz",
    ])
    d = tmp_path / "unrolled/barrel"
    assert _find_source(d / "barrel_n4_k008_bug.dqdimacs.gz", ".aag").name == "barrel_n4_bug.aag"
    assert _find_source(d / "barrel_n4_k008_safe.dqdimacs.gz", ".aag").name == "barrel_n4_safe.aag"


def test_sibling_variant_dir(tmp_path: Path) -> None:
    """inductive/barrel/X → unrolled/barrel/X.aag (broken before)."""
    _tree(tmp_path, [
        "unrolled/barrel/barrel_n4_safe.aag",
        "unrolled/barrel/barrel_n4_bug.aag",
        "succinct/barrel/barrel_n4_k008_safe.dqdimacs.gz",
        "inductive/barrel/barrel_n4_indinv_safe.dqdimacs.gz",
    ])
    suc = tmp_path / "succinct/barrel/barrel_n4_k008_safe.dqdimacs.gz"
    ind = tmp_path / "inductive/barrel/barrel_n4_indinv_safe.dqdimacs.gz"
    assert _find_source(suc, ".aag").name == "barrel_n4_safe.aag"
    assert _find_source(ind, ".aag").name == "barrel_n4_safe.aag"


def test_hwmc_indinv_prefix_token(tmp_path: Path) -> None:
    """indinv_gray_n32 → gray_n32.aag (same dir; broken before)."""
    _tree(tmp_path, [
        "inductive/gray_n32.aag",
        "inductive/gray_n4.aag",
        "inductive/indinv_gray_n32.dqdimacs.gz",
    ])
    inst = tmp_path / "inductive/indinv_gray_n32.dqdimacs.gz"
    assert _find_source(inst, ".aag").name == "gray_n32.aag"


def test_longest_match_wins(tmp_path: Path) -> None:
    """detector_unreal_n02 picks detector_unreal not detector."""
    _tree(tmp_path, [
        "x/detector.tlsf",
        "x/detector_unreal.tlsf",
        "x/detector_unreal_n02.dqdimacs.gz",
    ])
    inst = tmp_path / "x/detector_unreal_n02.dqdimacs.gz"
    assert _find_source(inst, ".tlsf").name == "detector_unreal.tlsf"


def test_no_cross_width_match(tmp_path: Path) -> None:
    """barrel_n12_k008_bug must not match barrel_n4_bug.aag."""
    _tree(tmp_path, [
        "unrolled/barrel/barrel_n4_bug.aag",
        "unrolled/barrel/barrel_n12_k008_bug.dqdimacs.gz",
    ])
    inst = tmp_path / "unrolled/barrel/barrel_n12_k008_bug.dqdimacs.gz"
    assert _find_source(inst, ".aag") is None


def test_no_match_returns_none(tmp_path: Path) -> None:
    _tree(tmp_path, ["a/b/x.dqdimacs.gz"])
    assert _find_source(tmp_path / "a/b/x.dqdimacs.gz", ".aag") is None
