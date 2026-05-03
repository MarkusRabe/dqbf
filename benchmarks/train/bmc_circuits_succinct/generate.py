"""bmc_circuits with the succinct (universal step-counter) encoding.

Same circuit library and (N,k) grid as `bmc_circuits/`; only the
encoding differs. See `tools.bmc2dqbf.encode.encode_succinct`.
"""

from __future__ import annotations

import sys

from benchmarks.train.bmc_circuits.generate import main

if __name__ == "__main__":
    sys.argv += ["--out", "benchmarks/train/bmc_circuits_succinct", "--mode", "succinct"]
    main()
