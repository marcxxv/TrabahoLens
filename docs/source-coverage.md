# Source coverage report

Every registered source audited against its primary source, as required by
finding 15. Regenerate the machine-readable form with `make build-release`
(`pipeline_stages` and `source_versions` in `data/release/manifest.json`).

Two official sources are retrieved and hash-verified: PSA LFS matrix 1B3FEMP4
and O*NET 31.0. Other rows below distinguish access, table suitability and
classification/crosswalk blockers.

---

## Corrections made during remediation

| Source | Problem found | Correction |
| --- | --- | --- |
| `psa_lfs` | `download_url` pointed at an obsolete PXWeb directory. | Pinned matrix 1B3FEMP4 and a 2024 Annual POST query; verified its `In thousands` unit and normalized to persons. |
| `psa_ows` | v1 targeted an industry-oriented table and conflated wage concepts. | Reviewed current O10/O20 tables; none satisfies coded-occupation average basic pay, so the metric stays unavailable. |
| `psa_sof` | `download_url` was a landing page. | Identified 2024 Table 2 XLSX; automated retrieval remains CDN-blocked. |
| `psa_informal` | No occupation-level source was ever identified; the entry implied one would soon be available. | Moved out of the planned core release. See below. |
| `psa_psoc` | Pointed at a landing page; version was "PSOC 2012" although the current publication is the **2022 Updates to the 2012 PSOC**. | Version corrected; entry records that the volume is the authoritative artifact. |
| `onet` | Pinned release 30.2 with no justification while 31.0 is current. | Re-pinned to 31.0 with a stated reason and an update policy. |
| `philjobnet`, `ibpap`, `dmw` | Registered `not_used`, which was correct. | Unchanged; conditions for future use retained. |

---

## Per-source state

| source_id | Authority | Retrieval | Table identified? | Parser | Metric state |
| --- | --- | --- | --- | --- | --- |
| `psa_psoc` | PH official statistical authority | token required | API identified | importer fixture-tested | classification unverified |
| `psa_lfs` | PH official statistical authority | retrieved + hashed | **yes** — matrix 1B3FEMP4 | real-source verified | 10 major-group estimates published |
| `psa_ows` | PH official statistical authority | reachable | no matching coded basic-pay table | fixture-tested | unavailable by definition mismatch |
| `psa_sof` | PH official statistical authority | CDN blocked | **yes** — 2024 Table 2 | XLSX parser pending | blocked |
| `psa_informal` | PH official statistical authority | not attempted | **no source identified** | none | removed from core release |
| `onet` | International official occupational | retrieved + hashed | yes — 31.0 archive | real-source verified (4 files) | blocked by missing accepted crosswalk |
| `philjobnet` | Other PH government | not used | n/a | none | not planned |
| `ibpap` | Industry | not used | n/a | none | not planned |
| `dmw` | Other PH government | not used | n/a | none | not planned |
| `llm_scoring` | Project-generated | blocked (403, no key) | n/a | run-manifest reader | blocked |

---

## OWS: what must be verified before any wage is published

Finding 15 requires these to be settled from the release itself, not assumed.
Review of the current tables resolved the first three negatively for this
metric: the available tables are industry/benchmark slices, publish average
wage rates rather than coded-occupation basic pay, and do not provide the
required concept. Coverage and exclusions remain documented constraints.

1. Occupation table versus industry table — v1 used the industry table.
2. Basic pay versus total earnings.
3. Mean versus median.
4. Establishment-size threshold.
5. Covered industries.
6. Excluded workers — agriculture, informal, own-account, unpaid family.

The parser refuses a file whose name identifies it as an industry table, but
that is a name check, not a substitute for reading the release notes.

## SOF: the conditional is fixed in the measure name

The identified 2024 table publishes **P(occupation | OFW)** directly as percent
distributions with measures of precision. The existing count-based parser is
not suitable for that workbook, so publication remains blocked until a
source-specific XLSX parser selects the all-OFW slice and preserves uncertainty.
There is no code path that produces P(OFW | occupation), because the compatible
denominator does not exist.

## Informality: removed from the planned core release

No occupation-level Philippine informality source has been identified. Leaving
the metric registered implied one was imminent. It is now recorded as
`blocked_by_unresolved_methodology` with no parser, and the two candidate
concepts are stated so a future attempt starts from the right question:

* **informal sector** — an enterprise characteristic;
* **informal employment** — a job characteristic.

They are different counts, and a release must say which it used.
