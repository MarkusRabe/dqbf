#!/usr/bin/env bash
# Fetch benchmark archives that are too large to commit.
# Small sets (QBFEVAL DQBF track) are committed directly; this script
# pulls the rest into benchmarks/_downloads/ and unpacks them.
#
# Security: every archive is checksum-pinned; extraction refuses entries
# with absolute paths or '..' components.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DL="$ROOT/benchmarks/_downloads"
mkdir -p "$DL"

fetch() {
  local url="$1" out="$2" sha="$3"
  if [[ -z "$sha" ]]; then
    echo "error: refusing to fetch $out without a pinned sha256" >&2
    echo "  run once with ALLOW_UNPINNED=1, record the hash below, then remove the override" >&2
    [[ "${ALLOW_UNPINNED:-}" == "1" ]] || exit 1
  fi
  if [[ -f "$DL/$out" ]] && echo "$sha  $DL/$out" | sha256sum -c --status 2>/dev/null; then
    echo "cached: $out"
    return
  fi
  echo "fetch:  $url"
  curl -fL --proto '=https' --tlsv1.2 "$url" -o "$DL/$out"
  if [[ -n "$sha" ]]; then
    echo "$sha  $DL/$out" | sha256sum -c
  else
    echo "UNPINNED sha256 for $out: $(sha256sum "$DL/$out" | cut -d' ' -f1)"
  fi
}

safe_extract() {
  local archive="$1" dest="$2"; shift 2
  local bad
  bad=$(tar -tf "$archive" "$@" | grep -E '(^/|(^|/)\.\.(/|$))' || true)
  if [[ -n "$bad" ]]; then
    echo "error: archive $archive contains unsafe paths:" >&2
    printf '  %s\n' "$bad" >&2
    exit 1
  fi
  bad=$(tar -tvf "$archive" "$@" | grep -E '^[lh]' || true)
  if [[ -n "$bad" ]]; then
    echo "error: archive $archive contains symlink/hardlink entries (refusing):" >&2
    printf '  %s\n' "$bad" >&2
    exit 1
  fi
  mkdir -p "$dest"
  tar -C "$dest" --no-same-owner --no-same-permissions -xf "$archive" "$@"
}

# --- QBFEVAL (large; QBF tracks) ---------------------------------------
# TODO: fill sha256 after first ALLOW_UNPINNED=1 run.
GALLERY="https://qbf23.pages.sai.jku.at/gallery"
fetch "$GALLERY/qdimacs.tar.xz"    qbfeval23_qdimacs.tar.xz  ""
fetch "$GALLERY/qdimacs20.tar.zst" qbfeval20_qdimacs.tar.zst ""
safe_extract "$DL/qbfeval23_qdimacs.tar.xz"  "$ROOT/benchmarks/holdout/qbf/qbfeval23"
safe_extract "$DL/qbfeval20_qdimacs.tar.zst" "$ROOT/benchmarks/holdout/qbf/qbfeval20" --zstd

# --- SMT-LIB BV (quantified) -------------------------------------------
ZENODO="https://zenodo.org/records/15493090/files"
fetch "$ZENODO/BV.tar.zst" smtlib_BV.tar.zst ""
safe_extract "$DL/smtlib_BV.tar.zst" "$ROOT/benchmarks/holdout/qbvf/bv" --zstd

echo "done. Large sets unpacked under benchmarks/{qbf,qbvf}/."
