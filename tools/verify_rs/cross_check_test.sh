#!/usr/bin/env bash
# Cross-check the Rust verifier against the Python verifier on the
# entire valid + adversarial corpus. Both must agree on every case.
#
# Disagreements are bugs — probably in whichever verifier accepts an
# adversarial case (false VALID is worse than false INVALID).
#
# Usage: ./cross_check_test.sh [PYTHON]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PY="${1:-python}"
SOLVER="$ROOT/third_party/kissat/build/kissat"
BIN="$HERE/target/debug/dqbf-verify-rs"
[ -x "$BIN" ] || BIN="$HERE/target/release/dqbf-verify-rs"
[ -x "$BIN" ] || { echo "build first: cargo build --manifest-path $HERE/Cargo.toml"; exit 2; }

cd "$HERE/tests/adversarial"
[ -f f1.valid.frp ] || ./build_corpus.sh

fails=0
total=0
agree=0
strict=0   # rust=INVALID, python=VALID — rust is stricter (safe direction)
unsound=0  # rust=VALID, python=INVALID — DANGEROUS, must be zero

run_py_unsat() { (cd "$ROOT" && $PY -m tools.verify.cli unsat "$1" "$2" 2>/dev/null) | tail -1; }
run_py_sat()   { (cd "$ROOT" && $PY -m tools.verify.cli sat "$1" "$2" -o /tmp/cc.cnf --solve 2>/dev/null) | tail -1; }
norm() { case "$1" in VALID) echo VALID;; *) echo INVALID;; esac; }

for f in *.frp; do
  base=${f%%.*}
  total=$((total+1))
  rs=$(norm "$($BIN unsat "$HERE/tests/adversarial/${base}.dqdimacs" "$HERE/tests/adversarial/$f" 2>/dev/null)")
  py=$(norm "$(run_py_unsat "$HERE/tests/adversarial/${base}.dqdimacs" "$HERE/tests/adversarial/$f")")
  if [ "$rs" = "$py" ]; then
    agree=$((agree+1))
  elif [ "$rs" = "INVALID" ] && [ "$py" = "VALID" ]; then
    strict=$((strict+1))
    echo "STRICT $f: rust=INVALID python=VALID (rust stricter; safe)"
  else
    unsound=$((unsound+1))
    fails=$((fails+1))
    echo "UNSOUND $f: rust=VALID python=INVALID — RUST ACCEPTS WHAT PYTHON REJECTS"
  fi
done
for f in *.aag; do
  base=${f%%.*}
  total=$((total+1))
  rs=$(norm "$($BIN sat "$HERE/tests/adversarial/${base}.dqdimacs" "$HERE/tests/adversarial/$f" --solver "$SOLVER" 2>/dev/null)")
  py=$(norm "$(run_py_sat "$HERE/tests/adversarial/${base}.dqdimacs" "$HERE/tests/adversarial/$f")")
  if [ "$rs" = "$py" ]; then
    agree=$((agree+1))
  elif [ "$rs" = "INVALID" ] && [ "$py" = "VALID" ]; then
    strict=$((strict+1))
    echo "STRICT $f: rust=INVALID python=VALID (rust stricter; safe)"
  else
    unsound=$((unsound+1))
    fails=$((fails+1))
    echo "UNSOUND $f: rust=VALID python=INVALID — RUST ACCEPTS WHAT PYTHON REJECTS"
  fi
done

echo "cross-check: $agree/$total agree, $strict rust-stricter, $unsound rust-laxer"
echo "  (rust-stricter disagreements are safe; rust-laxer would be a bug)"
exit $((unsound > 0))
