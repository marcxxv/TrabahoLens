# Legacy v1 dataset (archived, not published)

These files are the **verbatim** TrabahoLens v1 artifacts as they existed at
commit `128dd2238bc3e9657ab84467d0876ffbdf88f494`, copied here unchanged before
the v2 rebuild began. They are preserved so the baseline audit is reproducible
and so anyone reviewing the rebuild can compare claims against what was
actually shipped.

| File | What it was in v1 |
| --- | --- |
| `occupations_ph.csv` | main derived occupation table (173 rows) |
| `scores_ai_only.json` | single-run LLM exposure score cache (173 entries) |
| `occupations_seed.json` | manually curated seed records (44 entries) |
| `site_data.json` | the dataset the public site rendered (173 records) |
| `index_v1.html` | the v1 interface, kept for claim-by-claim comparison |

## These values are not evidence

Nothing in this directory may be read by the v2 pipeline, re-published, or
cited as a source. The baseline audit (`docs/audit/baseline-audit.md`)
establishes that the employment, wage, informality, OFW-share and
hiring-intensity values here are synthetic, constant-by-category, or
placeholder, and that the exposure scores were produced by a single
non-replicated model run under a prompt that anchored the score distribution.

They are retained as **evidence about v1**, not as evidence about the
Philippine labour market.

A validator (`tests/test_no_legacy_leakage.py`) fails the build if any v2
artifact reads from or reproduces these files.
