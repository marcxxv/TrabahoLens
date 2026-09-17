# Migration notes: v1 → v2

What moved, what was withdrawn, what still works, and how to read the old data.

---

## Nothing was deleted

Every v1 artifact is preserved verbatim in `data/legacy/v1/`, copied before any
rewrite began, at commit `128dd2238bc3e9657ab84467d0876ffbdf88f494`.

| Archived file | Was |
| --- | --- |
| `occupations_ph.csv` | `data/derived/occupations_ph.csv` (173 rows) |
| `scores_ai_only.json` | `data/derived/scores_ai_only.json` (173 entries) |
| `occupations_seed.json` | `data/reference/occupations_seed.json` (44 entries) |
| `site_data.json` | `site/data.json` (173 published records) |
| `index_v1.html` | `site/index.html` |

The copies were verified byte-identical (SHA-256) before the originals were
removed from their old locations. They were moved, not deleted, so a reader
cannot mistake a withdrawn dataset for a current one.

`data/derived/README.md` and `data/reference/README.md` point to the archive.

**These files are evidence about v1, not evidence about the Philippine labour
market.** A test (`test_no_v2_module_reads_the_legacy_dataset`) fails the build
if any v2 module reads them, checked over the parsed syntax tree so a docstring
mentioning the archive does not count as reading it.

---

## Code that was retired

These modules remain in `src/trabaholens/` because
[`docs/audit/baseline-audit.md`](audit/baseline-audit.md) cites them line by
line. Their `main()` now raises immediately; the original logic is preserved as
`_v1_main()` so it stays inspectable.

`assign_ph_stats` · `build_site_data` · `filter_ph_occupations` ·
`make_csv_ph` · `score_ai_only` · `fetch_onet` · `fetch_psa`

Their `scripts/` entrypoints were removed. Running any of them would regenerate
values the audit found to be synthetic, constant-by-category or placeholder —
and `build_site_data` would have overwritten the v2 release payload with the v1
format.

`pipeline_utils` and `validation` are untouched and still importable; the audit
profiler reads `GROUP_TOTALS` and `SOC_TO_PSOC_MAJOR` from them directly.

---

## Command changes

| v1 | v2 |
| --- | --- |
| `python scripts/build_site_data.py` | `make build-site` |
| `python scripts/check.py` | `make check` (now runs the release validator, not a title comparison) |
| `python scripts/score_ai_only.py` | `make score-exposure MODEL=<id>` |
| `python scripts/fetch_onet.py`, `fetch_psa.py` | `make fetch-data` (all registered sources, hashed, manifest-recorded) |
| — | `make audit`, `make build-metrics`, `make validate-release`, `make determinism`, `make sensitivity` |

`python scripts/serve.py` is unchanged.

---

## Field migration

| v1 field | v2 | Why |
| --- | --- | --- |
| `jobs` | `employment_count`, blocked | v1 value was a hard-coded group total split by title keywords |
| `pay` | `wage_basic_pay`, blocked | v1 value was a constant per category |
| `outlook` | **gone, no successor** | v1 value was the literal `50`; no source for it exists |
| `informal_share` | **gone, no current core successor** | v1 value was a constant per category; no occupation-level Philippine source is identified |
| `ofw_share` | `ofw_distribution_share`, blocked | **different quantity** — see below |
| `education` | `onet_job_zone`, blocked | Retained but relabelled a US-derived proxy |
| `exposure` (0–10) | two 0–5 model-scored dimensions, no score published | v1 was one unreplicated run under an anchored prompt |
| `exposure_rationale` | returns only with a model-derived badge | v1 displayed model text as explanation of fact |
| `primary_risk_vector` | `ai_can_assist_with` / `remains_human_dependent` | Hazard vocabulary removed |
| `category` | **gone** | An internal 22-bucket string that drove the wage and informality constants |
| `source` | **gone** | Recorded which code branch ran, not where a number came from |
| — | `derivation_class`, `source_authority`, `availability`, `confidence_grade`, `source_granularity`, `display_granularity`, `source_url`, `source_file_hash`, `retrieved_at`, `reference_period` | New. Provenance now travels with every value |

### The OFW field is not a rename

`ofw_share` → `ofw_distribution_share` changes **what is being measured**.

- v1's `ofw_share` was presented as the share of an occupation's workers who are
  overseas: **P(OFW | occupation)**.
- The values were actually the distribution of OFWs across occupation groups:
  **P(occupation | OFW)**. The audit proved it — v1's nine group constants sum
  to 1.02.

v2 publishes only the distribution, under its own name, with the denominator
stated. Do not map one onto the other in any downstream comparison.

---

## Identifier migration

v1 keyed on `ONET-<SOC code>` with `PH-000N` for ten hand-written records. v2
keys on `PSOC-<code>`.

**There is no id crosswalk, and one should not be constructed.** v1's 173 rows
were US O\*NET titles selected by keyword ranking; mapping them onto PSOC codes
after the fact would reproduce exactly the heuristic the rebuild removed. v1's
SOC→PSOC mapping is preserved in
`data/canonical/crosswalk_psoc_isco_soc.csv` with `review_status = rejected`
so the break is auditable, and a validator refuses any observation that resolves
through it.

---

## Reading the v1 data

```bash
make audit          # regenerate docs/audit/current-data-profile.json
```

The profiler is the only supported way to read the archive. It reports record
counts, distributions, repeated-value clusters, group-total reconciliation,
crosswalk cardinality, aggregate/component overlap, the OFW denominator test and
determinism — the evidence behind every removal above.

---

## If you depended on v1's `site/data.json`

The payload shape changed completely: v1 was a flat array of 173 occupation
objects; v2 is an object with `schema`, `release`, `disclaimers`, legends,
`metrics`, `counts` and `occupations`.

If you were consuming v1's array, **do not port to v2 expecting equivalent
numbers.** There are none, by design. The archived v1 payload is at
`data/legacy/v1/site_data.json` if you need to reproduce a historical chart —
with the caveat that the baseline audit explains what each of its fields
actually was.
