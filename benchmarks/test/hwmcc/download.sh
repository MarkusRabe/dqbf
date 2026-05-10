#!/usr/bin/env bash
# Fetch HWMCC AIGER benchmarks into instances/ (gitignored).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DL="$HERE/../../_downloads"
mkdir -p "$DL" "$HERE/instances"

# HWMCC'20 bit-vector track (AIGER), pinned to the archive served on
# 2026-05-10. If fmv.jku.at re-publishes the archive, update the
# sha256 only after manually verifying the change is intentional.
SHA256="f748b9634c9e08326b98203af8ab4880869e408f2e42f6e02f31f0c70731272a"
URL="https://fmv.jku.at/hwmcc20/hwmcc20benchmarks.tar.xz"
OUT="$DL/hwmcc20benchmarks.tar.xz"
if [[ ! -f "$OUT" ]]; then
  echo "fetching $URL"
  curl -fL --proto '=https' --tlsv1.2 "$URL" -o "$OUT"
fi
GOT="$(sha256sum "$OUT" | cut -d' ' -f1)"
if [[ "$GOT" != "$SHA256" ]]; then
  echo "sha256 mismatch: got $GOT, expected $SHA256" >&2
  echo "(remove $OUT and re-run if the archive was corrupted; review the" >&2
  echo " upstream change before updating SHA256 if it was re-published)" >&2
  exit 1
fi
echo "sha256 ok: $GOT"

# Per-instance results (for expected verdicts) — same provenance.
RESULTS_URL="https://fmv.jku.at/hwmcc20/hwmcc20-bv-all.csv"
RESULTS_OUT="$DL/hwmcc20-bv-all.csv"
RESULTS_SHA256="5d5a9adcc20d270a4fa0d4bc0a1db09a71ef6649fd9602617af55f2a2211bd06"
if [[ ! -f "$RESULTS_OUT" ]]; then
  curl -fL --proto '=https' --tlsv1.2 "$RESULTS_URL" -o "$RESULTS_OUT"
fi
RGOT="$(sha256sum "$RESULTS_OUT" | cut -d' ' -f1)"
[[ "$RGOT" == "$RESULTS_SHA256" ]] || { echo "results CSV sha256 mismatch" >&2; exit 1; }

# Extract only the AIGER subtree; reject unsafe paths.
bad=$(tar -tf "$OUT" | grep -E '(^/|(^|/)\.\.(/|$))' || true)
[[ -z "$bad" ]] || { echo "unsafe paths in archive"; exit 1; }
tar -C "$HERE/instances" --no-same-owner -xf "$OUT" --wildcards '*/aig/*' 2>/dev/null \
  || tar -C "$HERE/instances" --no-same-owner -xf "$OUT"
echo "done: $(find "$HERE/instances" -name '*.aig' -o -name '*.aag' | wc -l) AIGER files"
