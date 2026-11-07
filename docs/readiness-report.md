# Readiness report

Source review: 2026-09-28. **Local research preview; not yet an approved
production exposure product.** No merge, push or deployment is implied.

| Component | Status |
| --- | --- |
| Forensic v1 audit | Implemented; legacy numeric values remain withdrawn |
| Classification | Official PSOC workbook imported; source count discrepancy disclosed |
| Employment | Real-source verified at major-group level |
| OFW distribution | Real-source verified, with source uncertainty and one missing cell |
| Wage references | Real-source verified at job-position × industry level; nine records quarantined |
| Canonical occupational basic pay | Unavailable; wage concept/version mismatch unresolved |
| O*NET Philippine correspondence | Missing; no title-similarity substitute |
| Exposure model run and expert review | Full task-file run, experimental: 447 of 447 PSOC unit groups with PSA tasks scored (894 dimension scores) from 3,318 of 3,362 statements, `deepseek-v4.1-flash` via NYO, 2 attempts at temperature 0; not human-reviewed; multi-model agreement measured, no independent validation |
| Interface | Deployed CSS, structure and interaction model restored; 61/61 headless-Chrome checks pass (`make browser-qa`) at desktop, tablet and phone sizes; user acceptance on real devices pending |
| External integration | Philippine AI Report public API checked; HTTP 402 provider quota restriction; no survey values imported |

## Data delivered by this pass

The canonical observation table has 102 published values: 10 PSA LFS employment
and nine SOF, plus 83 from ILOSTAT (43 sub-major employment, 10 mean and 10
median employee earnings, 10 advanced-education shares, 10 own-account and
family work shares).
A separate source-native wage reference table has 684 available records and nine
withheld rows. These are not 684 unique national occupations. Classification
units are not counts of occupations with measured data.

PSA's public XLSX downloads made PSOC, SOF and OWS accessible despite the
automated CDN failures. The retained source files, hash pins and real-workbook
tests close the previous fixture-only gap for these exact source formats.

## Remaining gates

1. Confirm the OWS occupational code version and obtain a defensible detailed
   correspondence before any PSOC wage join.
2. Resolve the PSOC workbook/webpage unit-count discrepancy with the publisher.
3. Complete human review of the full task-based scoring run and independent
   validation of the exposure scale before activating AI task exposure as a
   product. Coverage and repeated scoring are done; human review is not.
4. Obtain independent Philippine statistical/methodological review.
5. Review the data release and the browser-QA screenshots, and test on real
   devices, before deciding whether to deploy the limited evidence explorer. Deployment of the limited explorer would not
   make the missing exposure product complete.
6. Obtain detailed PSA employment estimates with classification and precision
   before restoring detailed employment-sized occupation boxes. The current map
   has genuine major-group estimates, not allocations to detailed occupations.

See `docs/data-completion-requests.md` for the specific publisher requests,
what requires human review, and the Philippine AI Report API result. Passing
the automated suite does not establish visual parity with the deployed site.

No missing layer is filled for visual completeness. Automated checks do not
prove source statistics are error-free. Detailed source scope and caveats are
in `docs/limitations.md`.
