#!/usr/bin/env bash
# Fetch benchmark archives that are too large to commit.
# Small sets (QBFEVAL DQBF, HQS, SMT-LIB UFBV/ABV) are committed directly;
# this script pulls the rest into benchmarks/_downloads/ and unpacks them.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DL="$ROOT/benchmarks/_downloads"
mkdir -p "$DL"

fetch() {
  local url="$1" out="$2" sha="$3"
  if [[ -f "$DL/$out" ]] && echo "$sha  $DL/$out" | sha256sum -c --status 2>/dev/null; then
    echo "cached: $out"
    return
  fi
  echo "fetch:  $url"
  curl -fL "$url" -o "$DL/$out"
  if [[ -n "$sha" ]]; then
    echo "$sha  $DL/$out" | sha256sum -c
  fi
}

# --- QBFEVAL (large; QBF + QCIR tracks) ---------------------------------
GALLERY="https://qbf23.pages.sai.jku.at/gallery"
fetch "$GALLERY/qdimacs.tar.xz"   qbfeval23_qdimacs.tar.xz   ""
fetch "$GALLERY/qdimacs20.tar.zst" qbfeval20_qdimacs.tar.zst ""
# fetch "$GALLERY/qcir.tar.xz"    qbfeval23_qcir.tar.xz      ""   # 640MB; uncomment if needed

mkdir -p "$ROOT/benchmarks/qbf/qbfeval23" "$ROOT/benchmarks/qbf/qbfeval20"
tar -C "$ROOT/benchmarks/qbf/qbfeval23" -xf "$DL/qbfeval23_qdimacs.tar.xz"
tar -C "$ROOT/benchmarks/qbf/qbfeval20" --zstd -xf "$DL/qbfeval20_qdimacs.tar.zst"

# --- SMT-LIB BV (quantified) -------------------------------------------
ZENODO="https://zenodo.org/records/15493090/files"
fetch "$ZENODO/BV.tar.zst" smtlib_BV.tar.zst ""
mkdir -p "$ROOT/benchmarks/qbvf/bv"
tar -C "$ROOT/benchmarks/qbvf/bv" --zstd -xf "$DL/smtlib_BV.tar.zst"

echo "done. Large sets unpacked under benchmarks/{qbf,qbvf}/."
