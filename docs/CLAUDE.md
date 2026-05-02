# docs/

Reference material that doesn't belong in code. **Not** user-facing
documentation (that's `README.md` + `OVERVIEW.md`); this is specs,
cached source material, plans, and accumulated dev reports.

```
IMPROVEMENT_LOOP.md           prover-improvement loop architecture and prerequisites
dev_reports/                  timestamped HTML status reports (committed; README.md is the index)
references/
  dqdimacs.md                 our write-up of the DQDIMACS format
  fork_resolution_journal/    mirror of the .tex source (rule definitions)
  local/                      copyright PDFs (gitignored; README.md says how to recreate)
```

Don't commit PDFs whose license is unclear; commit a `.md` with the
citation + URL instead.
