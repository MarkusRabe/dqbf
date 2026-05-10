#!/usr/bin/env bash
# Sparse-clone SYNTCOMP TLSF benchmarks into instances/ (gitignored)
# at a pinned commit. Pinning a commit (not a branch) is reproducible
# and tamper-evident — sha256 doesn't apply to git fetches.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="$HERE/instances"
DL="$HERE/../../_downloads"
mkdir -p "$DL"

# SYNTCOMP/benchmarks pinned to the commit fetched on 2026-05-10.
# Update only after manually reviewing the upstream change.
COMMIT="4105caf1f1e5fd3b76657879bfce8021d130cbde"
if [[ ! -d "$DST/.git" ]]; then
  git clone --filter=blob:none --sparse https://github.com/SYNTCOMP/benchmarks "$DST"
  git -C "$DST" sparse-checkout set tlsf
fi
git -C "$DST" fetch origin "$COMMIT"
git -C "$DST" checkout -q "$COMMIT"
echo "TLSF benchmarks @ $COMMIT: $(find "$DST" -name '*.tlsf' | wc -l) files"

# Realizability reference (for `expected`) — meyerphi/syntcomp-reference,
# pinned to the commit reviewed on 2026-05-10.
REF_COMMIT="66ced6d6207d7be919f905546c40701303a46aa3"
REF_DIR="$DL/syntcomp-reference"
if [[ ! -d "$REF_DIR/.git" ]]; then
  git clone --depth 1 https://github.com/meyerphi/syntcomp-reference "$REF_DIR"
fi
git -C "$REF_DIR" fetch origin "$REF_COMMIT" 2>/dev/null || true
git -C "$REF_DIR" checkout -q "$REF_COMMIT"
cp "$REF_DIR/results_verification.csv" "$DL/syntcomp_results.csv"
echo "results @ $REF_COMMIT"
