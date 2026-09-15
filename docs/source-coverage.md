# Source coverage report

Every registered source audited against its primary source, as required by
finding 15. Regenerate the machine-readable form with `make build-release`
(`pipeline_stages` and `source_versions` in `data/release/manifest.json`).

**No source has been retrieved in this environment.** Every host returned HTTP
403 at the egress proxy. The audit below is therefore of the *registry entries*
— their titles, URLs, universes, exclusions and licensing — not of retrieved
data.

---

## Corrections made during remediation

| Source | Problem found | Correction |
| --- | --- | --- |
| `psa_lfs` | `download_url` pointed at the PXWeb **API directory** `.../DB/DB__1B__LFS/`, which lists tables rather than being one. Registering a directory as a dataset implies a confirmed table endpoint that does not exist. | Marked `table_identification: unconfirmed`; the specific table id must be established before the metric is implementable. |
| `psa_ows` | Same directory-as-dataset problem. v1 had additionally targeted an **industry** table. | Directory flagged; the parser now refuses a file whose name identifies it as an industry table. |
| `psa_sof` | `download_url` was a **landing page**, described as if it were a downloadable table. | Marked `landing_page`, not `dataset`. |
| `psa_informal` | No occupation-level source was ever identified; the entry implied one would soon be available. | Moved out of the planned core release. See below. |
| `psa_psoc` | Pointed at a landing page; version was "PSOC 2012" although the current publication is the **2022 Updates to the 2012 PSOC**. | Version corrected; entry records that the volume is the authoritative artifact. |
| `onet` | Pinned release 30.2 with no justification while 31.0 is current. | Re-pinned to 31.0 with a stated reason and an update policy. |
| `philjobnet`, `ibpap`, `dmw` | Registered `not_used`, which was correct. | Unchanged; conditions for future use retained. |

---

## Per-source state

| source_id | Authority | Retrieval | Table identified? | Parser | Metric state |
| --- | --- | --- | --- | --- | --- |
| `psa_psoc` | PH official statistical authority | blocked (403) | volume, not a table | importer fixture-tested | classification unverified |
| `psa_lfs` | PH official statistical authority | blocked (403) | **no** — directory only | fixture-tested | blocked |
| `psa_ows` | PH official statistical authority | blocked (403) | **no** — directory only | fixture-tested | blocked |
| `psa_sof` | PH official statistical authority | blocked (403) | **no** — landing page | fixture-tested | blocked |
| `psa_informal` | PH official statistical authority | blocked (403) | **no source exists** | none | removed from core release |
| `onet` | International official occupational | blocked (403) | yes — pinned archive URL | fixture-tested (4 files) | blocked |
| `philjobnet` | Other PH government | not used | n/a | none | not planned |
| `ibpap` | Industry | not used | n/a | none | not planned |
| `dmw` | Other PH government | not used | n/a | none | not planned |
| `llm_scoring` | Project-generated | blocked (403, no key) | n/a | run-manifest reader | blocked |

---

## OWS: what must be verified before any wage is published

Finding 15 requires these to be settled from the release itself, not assumed.
All six remain **unverified**:

1. Occupation table versus industry table — v1 used the industry table.
2. Basic pay versus total earnings.
3. Mean versus median.
4. Establishment-size threshold.
5. Covered industries.
6. Excluded workers — agriculture, informal, own-account, unpaid family.

The parser refuses a file whose name identifies it as an industry table, but
that is a name check, not a substitute for reading the release notes.

## SOF: the conditional is fixed in the measure name

The parser emits `ofw_count_by_major_occupation` and the transformation
`T-012-sof-distribution` divides by the all-OFW total, producing
**P(occupation | OFW)**. The metric is named `ofw_distribution_share`. There is
no code path that produces P(OFW | occupation), because the compatible
denominator does not exist.

## Informality: removed from the planned core release

No occupation-level Philippine informality source has been identified. Leaving
the metric registered implied one was imminent. It is now recorded as
`blocked_by_unresolved_methodology` with no parser, and the two candidate
concepts are stated so a future attempt starts from the right question:

* **informal sector** — an enterprise characteristic;
* **informal employment** — a job characteristic.

They are different counts, and a release must say which it used.
