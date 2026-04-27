# SMT-LIB UFBV — fetch via script

**Not committed.** `UFBV.tar.zst` (1.7 MB) from
https://zenodo.org/records/15493090 unpacks to ≈ 1 GB across the
`wintersteiger/`, `Alive2/`, `PEak/`, and `Certora/` families. Use
`scripts/download_benchmarks.sh` (add a UFBV stanza) or fetch directly:

```
curl -fL https://zenodo.org/api/records/15493090/files/UFBV.tar.zst/content | tar --zstd -x
```

License: per-file CC-BY 4.0 (SMT-LIB).
