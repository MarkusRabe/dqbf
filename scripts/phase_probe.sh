#!/bin/bash
# Iteration probe for phase-interleave experiments.
set -uo pipefail
export PATH="/root/opensrc/dqbf/third_party/kissat/build:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cd provers/frust && cargo build --release 2>&1 | grep -E 'error\[|Finished' || exit 1
cargo test --release 2>&1 | grep 'test result' || true
cargo fmt
cd "$ROOT"

echo "=== tiny ==="
ok=1
for f in tests/integration/tiny/*.dqdimacs; do
  rm -f /tmp/c.aag /tmp/p.frp
  provers/frust/target/release/frust "$f" --cert /tmp/c.aag --proof /tmp/p.frp >/dev/null 2>&1; rc=$?
  printf "%-28s rc=%-3d " "$(basename "$f")" "$rc"
  if [ "$rc" -eq 10 ]; then
    out=$(/tmp/dqbf-venv/bin/python -m tools.verify.cli sat "$f" /tmp/c.aag -o /tmp/v.cnf --solve 2>&1 | tail -1)
    echo "$out"; [[ "$out" == *INVALID* ]] && ok=0
  elif [ "$rc" -eq 20 ]; then
    if [ -f /tmp/p.frp ]; then
      out=$(/tmp/dqbf-venv/bin/python -m tools.verify.cli unsat "$f" /tmp/p.frp 2>&1 | tail -1)
      echo "$out"; [[ "$out" == *INVALID* ]] && ok=0
    else echo "(no proof)"; fi
  else echo "(unknown)"; fi
done
[ "$ok" -eq 0 ] && { echo "!!! INVALID CERT IN TINY"; exit 2; }

echo "=== probe ==="
PATH="/root/opensrc/dqbf/third_party/kissat/build:$PATH" /tmp/dqbf-venv/bin/python scripts/frust_opt_loop.py 2>&1 | tail -22
