# Pre-integration readiness report

Post-remediation. Supersedes the version on `audit/rebuild-v2`, which overstated
completion in ways an independent review caught — see
[`remediation-review.md`](remediation-review.md).

**Question:** is TrabahoLens ready to become the workforce layer of Philippine
AI Report?

**Answer: no.** Unchanged from the previous report, but for a more precisely
stated reason. The previous report said the methodology was ready and only the
data was missing. That was wrong: parsing, classification reconciliation and
source-to-observation construction did not exist either. They exist now and are
fixture-tested, and **no stage has processed a real primary source**.

---

## Phase classification

The brief requires each phase to be classified as: complete and verified with
real primary-source data · implemented but tested only with fixtures ·
partially implemented · blocked · rejected.

| Phase | Classification | Why |
| --- | --- | --- |
| **Phase 1 — credibility reset** | **Complete and verified** | This phase's deliverable is the removal of unsupported claims and the honest labelling of what remains. That is verifiable against the repository itself, and it is done: unsupported metrics withdrawn, two evidence axes shown separately, per-stage status displayed, disclaimer fixed, counts derived, no hazard framing, no hard-coded counts. It does not depend on primary-source access. |
| **Phase 2 — Philippine-first data foundation** | **Implemented, fixture-tested only** | The pipeline runs end to end and a populated fixture publishes six observations with full provenance. No primary source has been retrieved, so no stage has seen real data. The PSOC classification is the ISCO-08 skeleton, unverified. Detailed occupations do not exist. |
| **Phase 3 — generative-AI task exposure** | **Partially implemented** | The rubric, prompt, harness, attempt accounting, ordinal aggregation and deterministic confidence are implemented and fixture-tested. Dimension C is **rejected** (removed, not deferred). The measure cannot run at all: it needs O\*NET task statements and a PSOC↔O\*NET crosswalk, and neither exists. |
| **Phase 4 — Philippine AI Report integration** | **Not started, correctly** | Out of scope by instruction, and blocked on Phases 2 and 3 regardless. |

### Per-stage detail

Machine-readable in `data/release/manifest.json` → `pipeline_stages`, and
rendered in the interface.

| Stage | Status |
| --- | --- |
| Source registry | implemented, verified with real source |
| Retrieval | blocked by source access |
| Raw snapshot | blocked by source access |
| Hash verification | implemented, fixture-tested only |
| Format validation | implemented, fixture-tested only |
| Parsing | implemented, fixture-tested only |
| Normalised source table | implemented, fixture-tested only |
| Classification reconciliation | partially implemented |
| Transformation | implemented, fixture-tested only |
| Canonical observation | implemented, fixture-tested only |
| Release validation | implemented, verified with real source |
| Site payload | implemented, verified with real source |

"Verified with real source" for the last two means they run on every build
against the actual committed artifacts — not that they have seen survey data.

---

## Direct answers

### Which data are official?

**None.** No source has been retrieved. Four metrics are *defined* to come from
the Philippine Statistics Authority, which is a source-authority claim, not a
derivation claim — see the next answer.

### Which are calculated?

**None published.** One is defined and fixture-proven: `ofw_distribution_share`
divides SOF occupation counts by the all-OFW total. The fixture confirms the
shares sum to 1.0.

### Which are estimated?

**Four, by definition; none published.** `employment_count`, `wage_basic_pay`,
`ofw_distribution_share` and `informal_employment_share` all derive from sample
surveys and carry sampling error.

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

Every source. `psa.gov.ph`, `openstat.psa.gov.ph`, `www.onetcenter.org` and
`openrouter.ai` all return HTTP 403 at this environment's egress proxy. Dated
attempts are in `data/sources/retrieval-manifest.json`.

Additionally, and independent of the network: the specific LFS, OWS and SOF
**tables** have not been identified. The registry entries point at PXWeb API
directories and landing pages, now flagged as such. Identifying the tables is
work that must happen before those metrics are implementable, and it is not
merely a matter of gaining access.

### What still requires independent expert validation?

1. The exposure rubric — no labour economist has reviewed it.
2. Any future exposure score — the full validation battery is specified and
   unexecuted.
3. The PSOC code list — needs a Philippine labour statistician against the
   PSA volume.
4. Metric definitions and denominators, particularly the OFW conditional and the
   informality concept.
5. The crosswalk — every edge is `machine_proposed`; none is `human_reviewed`.
6. Licensing — a good-faith reading, not reviewed by counsel. The PSA CC BY 4.0
   statement is recorded from documentation and **has not been confirmed against
   the live page**.

### Is the branch suitable for merge, production deployment, or Philippine AI Report integration?

| | Verdict |
| --- | --- |
| **Merge to `main`** | **Defensible, with one condition.** The branch is strictly more honest than `main`, which still publishes fabricated employment, wages and hiring intensity. Merging would replace false numbers with no numbers and a documented account of why. The condition: whoever merges must accept that the public site will show no metric values until sources are retrieved. That is a product decision, not a technical one. |
| **Production deployment** | **No.** Not because the code is unsafe, but because there is nothing to deploy *for*. A public page with zero metric values is a statement of intent; deploy it only if that statement is the intended product. |
| **Philippine AI Report integration** | **No.** Blocked on all of: real primary-source data, an identified table per metric, a verified PSOC classification, a reviewed crosswalk, and at least one completed exposure run with its validation battery. |

---

## What would change each verdict

1. **Retrieve the sources.** `make fetch-data` from a permitted network. The
   pipeline is written and fixture-proven; this is the single largest unblock.
2. **Identify the specific tables.** Independent of network access and
   currently unknown for LFS, OWS and SOF.
3. **Import the PSOC volume.** Unblocks detailed occupations, which three
   metrics need in order to have any unit to attach to.
4. **Retrieve the correspondences.** PSOC↔ISCO-08, ISCO-08↔SOC, SOC↔O\*NET.
   Without them the exposure measure cannot be task-based, and a non-task-based
   version would be v1 again.
5. **Human review.** Classification, crosswalk and rubric.

Items 1–3 alone would produce a real workforce layer: fewer metrics than v1,
broader occupational groups, visible gaps, every number traceable. Items 4–5
gate the exposure layer specifically, and it should be integrated last and
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
