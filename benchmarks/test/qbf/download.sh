#!/usr/bin/env bash
# Fetch QBFLIB QDIMACS benchmark archive and extract a representative
# subset (~150 instances across contributors). The full archive is
# ~10 GB compressed (28k instances) — only the subset is committed.
#
# To regenerate: run this script, then `python -m benchmarks.test.generate`.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DL="$HERE/../../_downloads"
mkdir -p "$DL" "$HERE/instances"

URL="https://www.qbflib.org/DOWNLOADS/qdimacs.zip"
OUT="$DL/qdimacs.zip"
SHA256="$(cat "$HERE/qdimacs.zip.sha256" 2>/dev/null || echo "")"

if [ ! -f "$OUT" ]; then
  echo "Downloading $URL (~10 GB, this takes a while)..."
  curl -L -C - -o "$OUT" "$URL"
fi
if [ -n "$SHA256" ]; then
  echo "$SHA256  $OUT" | sha256sum -c - || { echo "sha256 mismatch — re-download"; exit 1; }
else
  sha256sum "$OUT" | awk '{print $1}' > "$HERE/qdimacs.zip.sha256"
fi

# Extract a representative subset: up to 5 instances per contributor,
# size 100B-200KB (small enough for the 10s budget).
unzip -l "$OUT" | grep -E '^\s*[0-9]+\s+\S+\s+\S+\s+qdimacs/[A-Za-z][^/]+/.*\.qdimacs(\.gz)?$' | \
  grep -v __MACOSX | grep -v '/\._' | \
  awk '{print $1, $4}' | \
  awk -F'[ /]' '{c=$3; if (count[c]<5 && $1 < 200000 && $1 > 100) { print $2; count[c]++ }}' | head -150 | \
  while read f; do unzip -qq -j -o "$OUT" "$f" -d "$HERE/instances/"; done
find "$HERE/instances" -name '*.qdimacs' ! -name '*.gz' -exec gzip -9 {} \;
echo "$(ls "$HERE/instances" | wc -l) QBF instances in $HERE/instances/"
