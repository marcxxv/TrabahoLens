# Source coverage report

Reviewed 2026-09-28. State below distinguishes source acquisition from the
availability of a valid Philippine metric.

| Source | Retained evidence | Publication boundary |
| --- | --- | --- |
| PSA PSOC | Official 2022 XLSX, explicit hierarchy codes, SHA-256 pinned | Workbook imported; 466 vs webpage 456 unit-code discrepancy disclosed |
| PSA LFS | JSON-stat matrix 1B3FEMP4, 2024 annual slice | 10 major-group employment estimates; no detailed counts |
| PSA SOF | 2024 Table 2 XLSX, OFWs / both sexes / major occupation slice | Nine percentages with SE and CV; armed-forces blank remains missing |
| PSA OWS | 2024 SE CV workbook, published Table 1 columns A:H | 684 available source-native wage rates; nine inconsistent records withheld |
| O*NET 31.0 | Original database ZIP | No accepted PSOC correspondence; no Philippine proxy or model score published |
| PSA informality | No suitable occupation-level observation identified | Unavailable |
| PhilJobNet / IBPAP / DMW | Not used | No unsupported attribution or hiring signal |
| LLM scoring | No completed reviewed scoring run | Unavailable |

PSA's CDN rejects some automated requests. Normal public browser downloads
succeeded for the workbooks; no token or protected API was required. Successful
files are recorded in the append-only retrieval manifest. Failed attempts remain
in that history.

## Source-specific decisions

OWS wages are August 2024 means including regular cash allowances for full-time
time-rated workers in covered formal establishments with 10+ workers, including
agriculture. This differs from canonical `wage_basic_pay`, which stays
unavailable. The workbook labels source codes PSIC/PSOC but does not establish
the occupational version. We retain occupation × industry slices separately,
without an English-title crosswalk or domestic employment join.

SOF publishes P(occupation | OFW), not P(OFW | occupation). Only the all-OFW,
both-sexes occupation slice is extracted. Percentages and standard errors are
divided by 100, with no imputation, inferred counts or rescaling.

PSOC code columns are imported verbatim with leading zeros, parent checks,
uniqueness checks and a pinned expected workbook structure. ISCO correspondence
columns are not promoted to reviewed crosswalks merely because they exist.

## Reproducibility

Selected unmodified raw snapshots are allowlisted in `.gitignore`; unrelated
downloads stay ignored. The release records original URLs, dates and SHA-256.
Real-workbook regression tests read these files, not fixture tables shaped to
the parser. OWS release validation replays the raw source and compares every
reference record. See `docs/data-licenses.md` for attribution and terms.
