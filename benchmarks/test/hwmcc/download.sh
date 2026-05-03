#!/usr/bin/env bash
# Fetch HWMCC AIGER benchmarks into instances/ (gitignored).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DL="$HERE/../../_downloads"
mkdir -p "$DL" "$HERE/instances"

# HWMCC'20 bit-vector track (AIGER). Pin sha256 after first fetch.
URL="https://fmv.jku.at/hwmcc20/hwmcc20benchmarks.tar.xz"
OUT="$DL/hwmcc20benchmarks.tar.xz"
if [[ ! -f "$OUT" ]]; then
  echo "fetching $URL"
  curl -fL --proto '=https' --tlsv1.2 "$URL" -o "$OUT"
fi
echo "sha256: $(sha256sum "$OUT" | cut -d' ' -f1)"

# Extract only the AIGER subtree; reject unsafe paths.
bad=$(tar -tf "$OUT" | grep -E '(^/|(^|/)\.\.(/|$))' || true)
[[ -z "$bad" ]] || { echo "unsafe paths in archive"; exit 1; }
tar -C "$HERE/instances" --no-same-owner -xf "$OUT" --wildcards '*/aig/*' 2>/dev/null \
  || tar -C "$HERE/instances" --no-same-owner -xf "$OUT"
echo "done: $(find "$HERE/instances" -name '*.aig' -o -name '*.aag' | wc -l) AIGER files"
