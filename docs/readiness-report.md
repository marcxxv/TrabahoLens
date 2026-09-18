# Pre-integration readiness report

Post-remediation. Supersedes the version on `audit/rebuild-v2`, which overstated
completion in ways an independent review caught — see
[`remediation-review.md`](remediation-review.md).

**Question:** is TrabahoLens ready to become the workforce layer of Philippine
AI Report?

**Answer: not yet.** The first real workforce statistic now runs end to end:
the pinned 2024 annual PSA LFS table produces ten PSOC-major employment
estimates with hashes and complete provenance. O*NET 31.0 is also retrieved and
validated, but cannot yield Philippine observations without a reviewed
crosswalk. Detailed PSOC, wages, OFW distribution and exposure remain blocked.

---

## Phase classification

The brief requires each phase to be classified as: complete and verified with
real primary-source data · implemented but tested only with fixtures ·
partially implemented · blocked · rejected.

| Phase | Classification | Why |
| --- | --- | --- |
| **Phase 1 — credibility reset** | **Complete and verified** | This phase's deliverable is the removal of unsupported claims and the honest labelling of what remains. That is verifiable against the repository itself, and it is done: unsupported metrics withdrawn, two evidence axes shown separately, per-stage status displayed, disclaimer fixed, counts derived, no hazard framing, no hard-coded counts. It does not depend on primary-source access. |
| **Phase 2 — Philippine-first data foundation** | **Partially implemented, real-source verified for LFS** | Acquisition, hashing, JSON-stat parsing, unit normalization, version reconciliation, transformation and release publication are exercised against PSA matrix 1B3FEMP4. O*NET 31.0 is also hash-verified. The authoritative detailed PSOC list, a suitable OWS table, and the SOF workbook remain unavailable. |
| **Phase 3 — generative-AI task exposure** | **Partially implemented** | The rubric, prompt, harness, attempt accounting, ordinal aggregation and deterministic confidence are fixture-tested. O*NET task data now exist locally, but no accepted PSOC↔O*NET crosswalk or completed scoring run exists. Dimension C remains **rejected**. |
| **Phase 4 — Philippine AI Report integration** | **Not started, correctly** | Out of scope by instruction, and blocked on Phases 2 and 3 regardless. |

### Per-stage detail

Machine-readable in `data/release/manifest.json` → `pipeline_stages`, and
rendered in the interface.

| Stage | Status |
| --- | --- |
| Source registry | implemented, verified with real source |
| Retrieval | partially implemented — LFS and O*NET retrieved; other sources blocked |
| Raw snapshot | partially implemented — two verified snapshots |
| Hash verification | implemented, verified with real sources |
| Format validation | implemented, verified with real sources |
| Parsing | partially implemented — LFS and O*NET real-source verified |
| Normalised source table | partially implemented |
| Classification reconciliation | partially implemented |
| Transformation | partially implemented — LFS real-source verified |
| Canonical observation | partially implemented — ten published LFS rows |
| Release validation | implemented, verified with real source |
| Site payload | implemented, verified with real source |

"Verified with real source" for the last two means they run on every build
against the actual committed artifacts — not that they have seen survey data.

---

## Direct answers

### Which data are official?

**Ten official PSA estimates are published:** 2024 annual employed persons for
each PSOC major group. They remain `estimated`, not directly observed, because
LFS is a sample survey. No wage, OFW, O*NET or exposure value is published.

### Which are calculated?

**None published.** One is defined and fixture-proven: `ofw_distribution_share`
divides SOF occupation counts by the all-OFW total. The fixture confirms the
shares sum to 1.0.

### Which are estimated?

**Two by definition; one published.** `employment_count` is now published for
ten major groups. `wage_basic_pay` remains unavailable. The LFS table does not
publish sampling-error bounds, so the employment rows receive confidence B.
`ofw_distribution_share` is calculated from SOF survey-estimated counts.

This is the correction the review forced. The previous schema labelled these
`official_statistic` on a single axis, which read as "directly observed". PSA
publishing a figure makes it official; it does not make it observed. The axes
are now separate and **no metric is `directly_observed`** — the correct state,
not a gap.

### Which are proxies?

**One defined, none published.** `onet_job_zone` is a US O\*NET rating carried
across a crosswalk that does not yet exist.

Also proxy-adjacent and disclosed: the PSOC code list itself, derived from the
ISCO-08 skeleton rather than the PSA volume, `unverified_pending_source` on
every row.

### Which are model-derived?

**One defined, none published.** `gen_ai_task_exposure`, dimensions A and B.
`model_scores.csv` is header-only.

### Which current claims were unsupported?

From the original audit, all confirmed: occupation-level employment, wages,
hiring intensity, informal share, OFW share as the wrong conditional, exposure
as "risk", the PSA/PhilJobNet/IBPAP/POEA citations, and every headline derived
from them.

From this remediation, three further claims made by the *rebuild itself* were
unsupported and are corrected:

1. "The acquisition code, hashing, manifest and validators are complete and
   only source bytes are missing." Parsing, reconciliation and transformation
   did not exist.
2. `official_statistic` on four survey estimates.
3. `model_runs: []` hard-coded rather than derived.

### Which metrics were removed?

From v1: `jobs`, `pay`, `outlook`, `informal_share`, `ofw_share` as a share, the
0–10 exposure score, `primary_risk_vector`, `category`, `source`, and every
derived headline.

From the rebuild, in this remediation:

* **Exposure dimension C (adoption friction) — rejected.** Removed from model
  scoring entirely. The model was judging Philippine regulation, liability,
  connectivity, device access, employer scale and informality with no Philippine
  evidence.
* **Exposure dimension D (evidence confidence) — replaced.** Now computed
  deterministically from provenance.
* **`informal_employment_share` — removed from the planned core release.** No
  occupation-level Philippine source has been identified, and leaving it
  registered implied one was imminent.

### What source access remains unavailable?

The detailed PSOC API requires a personal PSA token. The exact SOF 2024 Table 2
is identified, but its XLSX returns a CDN verification response to automated
retrieval. OpenRouter still lacks a usable run/key. OWS is reachable, but the
reviewed tables do not supply the registered coded-occupation average-basic-pay
metric. LFS and O*NET are now reachable and retrieved.

### What still requires independent expert validation?

1. The exposure rubric — no labour economist has reviewed it.
2. Any future exposure score — the full validation battery is specified and
   unexecuted.
3. The PSOC code list — needs a Philippine labour statistician against the
   PSA volume.
4. Metric definitions and denominators, particularly the OFW conditional and the
   informality concept.
5. The crosswalk — every edge is `machine_proposed`; none is `human_reviewed`.
6. Licensing — the PSA site-wide CC BY 4.0 notice was confirmed, but this
   remains a good-faith reading not reviewed by counsel; dataset-specific
   exceptions must still be checked.

### Is the branch suitable for merge, production deployment, or Philippine AI Report integration?

| | Verdict |
| --- | --- |
| **Merge to `main`** | **Technically defensible after review.** The branch replaces fabricated v1 values with ten traceable PSA LFS estimates and explicit gaps. It should still be reviewed as a data release, not merged as routine UI work. |
| **Production deployment** | **Not yet recommended.** Employment is real and traceable, but the classification is aggregate/unverified below major level and four of five metrics have no published values. |
| **Philippine AI Report integration** | **No.** One primary metric is real, but integration still lacks a verified detailed PSOC classification, sufficient source coverage, a reviewed crosswalk, and a completed exposure run with its validation battery. |

---

## What would change each verdict

1. **Finish exact-source ingestion.** LFS is complete. Acquire and parse SOF
   2024 Table 2; keep OWS unavailable unless a table matching the metric appears.
2. **Obtain a PSOC API token and import the full 2022 classification.** This
   unblocks detailed occupations, which three metrics need as canonical units.
3. **Retrieve the correspondences.** PSOC↔ISCO-08, ISCO-08↔SOC, SOC↔O\*NET.
   Without them the exposure measure cannot be task-based, and a non-task-based
   version would be v1 again.
4. **Human review.** Classification, crosswalk and rubric.

Items 1–2 produce the core workforce layer: fewer metrics than v1,
broader occupational groups, visible gaps, every number traceable. Items 4–5
Items 3–4 gate the exposure layer specifically, and it should be integrated last and
labelled experimental wherever it appears.

## The recommendation, unchanged

If Philippine AI Report needs a workforce layer before items 1–5 are done,
integrate the **evidence ledger** — the PSOC structure, the metric definitions,
the source registry, the pipeline-stage status and the gap map. It is
publishable today, it is genuinely useful because it says what is knowable about
Philippine occupational data and what is not, and it makes the later arrival of
real figures an improvement rather than a correction.

The one thing not to do is integrate v1's numbers while pointing at v2's
methodology.
