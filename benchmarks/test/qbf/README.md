# test/qbf — QBFEVAL PCNF (BLOCKED)

Plain-prefix QDIMACS instances from QBFEVAL. DQBF subsumes QBF, so
these would run on both the QBF backends (`cadet`/`caqe`/`rareqs`) and
the DQBF backends without any encoding step.

## Status: blocked on a download source (2026-05-10)

QBFEVAL instances are no longer hosted at a stable archive URL:

- `qbflib.org/QBFLIB/*.tar.gz`, `qbflib.org/QBFEVAL_22_DATASET/*` — 404.
- `qbf23.pages.sai.jku.at/gallery/` — empty page (the gallery is JS-
  rendered or moved).
- `gitlab.sai.jku.at/qbf` group — only `pyqbf` (no benchmark mirror).
- Zenodo — no QBFEVAL dataset record found.

The official pages (`www.qbflib.org`) only expose a per-instance web
UI behind a search form, which isn't suitable for a reproducible
`download.sh`.

## What unblocks this

Either of:
1. A versioned archive URL (e.g., a Zenodo DOI for QBFEVAL'23 PCNF).
2. The QBFLIB site exposing a CSV index with per-instance URLs that a
   `download.sh` can loop over.

When found, add `download.sh` (with a sha256 pin or a per-file
checksum manifest) and a `generate.py` that just writes manifests:
no encoding step is needed for QDIMACS.

`expected` should come from the QBFEVAL results table — never from a
solver probe (`feedback_no_solver_ground_truth.md`).
