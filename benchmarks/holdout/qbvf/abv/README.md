# SMT-LIB ABV — fetch via script

**Not committed.** `ABV.tar.zst` (1.2 MB) from
https://zenodo.org/records/15493090 unpacks to ≈ 29 MB across 4 975
`.smt2` files (UltimateAutomizer SV-COMP 2019/2023). Per-file gzip only
brings that to ≈ 20 MB, so it stays behind the download script:

```
curl -fL https://zenodo.org/api/records/15493090/files/ABV.tar.zst/content | tar --zstd -x
```

License: per-file CC-BY 4.0 (SMT-LIB).
