#!/usr/bin/env bash
# Sparse-clone SYNTCOMP TLSF benchmarks into instances/ (gitignored).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="$HERE/instances"

if [[ -d "$DST/.git" ]]; then
  git -C "$DST" pull --ff-only
else
  git clone --filter=blob:none --sparse \
    https://github.com/SYNTCOMP/benchmarks "$DST"
  git -C "$DST" sparse-checkout set tlsf
fi
echo "done: $(find "$DST" -name '*.tlsf' | wc -l) TLSF files"
