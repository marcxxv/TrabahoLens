# Pre-integration readiness report

**Question:** is TrabahoLens ready to become the workforce layer of Philippine
AI Report?

**Answer: no.** The methodology is ready. The data is not — this release
publishes no metric values, because no source could be retrieved from the build
environment. Integrating now would put a credible frame around an empty dataset,
which is a worse failure than the one this rebuild corrected: v1 at least looked
wrong to anyone who checked, whereas a well-documented empty layer invites
trust it has not yet earned.

What follows is component by component, then the direct answers.

---

## Component assessment

| Component | Status | Assessment |
| --- | --- | --- |
| Baseline audit | **Ready** | Reproducible via `make audit`; every claim traced to a code path and a profile field. |
| Legacy archive | **Ready** | Verbatim, hash-verified, isolated from v2 by a test. |
| PSOC schema and canonical model | **Ready with caveats** | Structure and vocabularies are sound. The code list is unverified against the PSA volume and every row says so. |
| PSOC code list contents | **Blocked by unavailable evidence** | `psa.gov.ph` unreachable. Entered from ISCO-08-aligned documentation. |
| Detailed occupations (minor/unit groups) | **Blocked by unavailable evidence** | Absent rather than guessed. Three metrics have no unit to attach to. |
| Source registry | **Ready** | 10 sources with universe, exclusions, period, licensing, attribution. |
| Retrieval manifest and acquisition | **Ready** | Code is complete, hashed, tested. Recorded dated 403s for every source. |
| Employment (LFS) | **Blocked by unavailable evidence** | Defined, sourced, blocked. Published granularity still unverified. |
| Wages (OWS) | **Blocked by unavailable evidence** | Plus: v1's targeted table was by industry. Needs an occupation table and the wage concept read off it. |
| OFW distribution (SOF) | **Blocked by unavailable evidence** | Metric redefined to what SOF supports. |
| Informality | **Blocked by unavailable evidence** | An occupational breakdown may not exist at all; unconfirmed. |
| O\*NET Job Zone | **Blocked by unavailable evidence** | `onetcenter.org` unreachable. Will be a US-derived proxy when retrieved. |
| Hiring intensity | **Remove** | Done. No source exists. Do not reintroduce without real posting data, and then only as a posting signal. |
| PhilJobNet / IBPAP / POEA citations | **Remove** | Done. Registered as `not_used` with conditions for future use. |
| PSOC↔ISCO crosswalk | **Ready with caveats** | Structural derivation, `machine_proposed`. Needs human review against the PSA volume. |
| PSOC↔SOC crosswalk | **Blocked by unavailable evidence** | Only v1's rejected heuristic exists. A real one needs both classifications in hand. |
| Exposure rubric v0.1.0 | **Experimental** | Coherent, versioned, prohibitions encoded. No expert review. |
| Exposure prompt v0.1.0 | **Experimental** | Anchor and synthetic inputs removed. Never executed. |
| Scoring harness | **Ready with caveats** | Guards and aggregation tested against a stub. Never run against a real model. |
| Exposure scores | **Blocked by unavailable evidence** | None exist. v1's are not a fallback. |
| Sensitivity and stability report | **Ready with caveats** | Generator works; reports honestly that no run exists. |
| Validation suite | **Ready** | Every check tested against a fixture that violates it. |
| Pipeline and CI | **Ready** | Deterministic build proven; CI fails on stale artifacts. |
| Interface | **Ready with caveats** | Evidence-first, disclaimer fixed, counts derived, no hazard framing. Untested with real users, and unexercised against populated data. |
| Documentation | **Ready** | Methodology, dictionary, limitations, licensing, protocol, migration, changelog. |
| Release manifest | **Ready** | Versions, hashes, per-source state, limitations. |

---

## Direct answers

### Which data are official?

**None in this release.** No official statistic has been retrieved.

Four metrics are *defined* to be official statistics when their sources arrive:
`employment_count` (PSA LFS), `wage_basic_pay` (PSA OWS),
`ofw_distribution_share` (PSA SOF), `informal_employment_share` (PSA).

### Which are calculated?

**None.** No calculated statistic exists, because there are no official inputs
to calculate from. The class is defined and the schema supports it.

### Which are estimated?

**None.** Survey-weighted estimation with standard errors is specified in the
methodology and the schema carries `uncertainty_lower` / `uncertainty_upper`,
but no microdata is in hand and the estimation code does not exist.

### Which are proxies?

**One is defined; none is published.** `onet_job_zone` is a US-derived proxy
for Philippine entry requirements, blocked pending O\*NET retrieval.

Also proxy-adjacent and disclosed as such: the PSOC code list itself, derived
from the ISCO-08 skeleton rather than the PSA volume, marked
`unverified_pending_source` on every row.

### Which are model-derived?

**One is defined; none is published.** `gen_ai_task_exposure` across four
dimensions. `model_scores.csv` is header-only.

### Which current claims were unsupported?

From the audit, all confirmed against the shipped data:

1. Occupation-level employment — synthetic.
2. Occupation-level wages — category constants.
3. Hiring intensity — the literal `50`, attributed to PhilJobNet and IBPAP.
4. Informal share — category constants.
5. OFW share — the wrong conditional; the nine constants sum to 1.02.
6. Exposure as "risk" — a single unreplicated run under an anchored prompt.
7. PSA LFS, OWS and SOF citations — no retrieval, no file, no URL.
8. PhilJobNet, IBPAP and POEA citations — nothing at all; POEA also superseded
   by DMW in 2022.
9. Total jobs, monthly payroll, wages exposed, OFW-linked jobs — arithmetic on
   the above.
10. "173 occupations" — accurate but hard-coded in two places.

The brief's hypothesis of a 500+ occupation claim is **not confirmed in this
repository**. No such claim exists in any commit. If it exists, it is on an
external surface this branch cannot see.

### Which metrics were removed?

`jobs`, `pay`, `outlook`, `informal_share`, `ofw_share` (as a share), the 0–10
exposure score, `primary_risk_vector`, `category`, `source`, and every derived
headline built on them.

`education` was retained and relabelled `onet_job_zone`, a US-derived proxy.

### What source access remains unavailable?

| Source | Blocker | Remedy |
| --- | --- | --- |
| PSA PSOC 2012 | `psa.gov.ph` 403 | Retrieve the volume; diff the code list |
| PSA LFS | `openstat.psa.gov.ph` 403 | `make fetch-data` from a permitted network; confirm published granularity |
| PSA OWS | `openstat.psa.gov.ph` 403 | Same; identify an **occupation** table and the wage concept |
| PSA SOF | `psa.gov.ph` 403 | Same; confirm the OFW definition used |
| PSA informality | `psa.gov.ph` 403 | First confirm an occupational table exists at all |
| O\*NET 30.2 | `onetcenter.org` 403 | `make fetch-data`; then task extraction |
| OpenRouter | `openrouter.ai` 403; no API key | Key plus a permitted network |
| PhilJobNet | No public bulk download or API identified | Establish access; do not scrape around an absent API |
| IBPAP | No occupational dataset identified | Industry-level only, with a documented mapping |
| DMW | No specific dataset identified | Name the table; deployments are a flow, not a stock |

### What still requires independent expert validation?

1. **The exposure rubric.** No labour economist has reviewed the dimensions,
   anchors or prohibitions.
2. **Any future exposure score.** The full validation battery in
   `exposure-protocol.md` is specified and unexecuted.
3. **The PSOC code list.** Needs a Philippine labour statistician against the
   PSA volume.
4. **Metric definitions and denominators**, particularly the OFW conditional and
   the informality concept.
5. **The crosswalk**, currently `machine_proposed`, never `human_reviewed`.
6. **Licensing**, a good-faith reading not reviewed by counsel.

### Is TrabahoLens ready to become the workforce layer of Philippine AI Report?

**No.**

### What remains blocking?

In order.

1. **No data.** Every metric is `blocked_pending_source`. This is the whole
   blocker; the rest are conditions on doing it properly.
2. **No occupational resolution.** Without PSOC minor and unit groups, the
   canonical table holds 53 aggregates and cannot carry an occupation-level
   metric at all.
3. **No exposure score, and none possible yet.** Task evidence is blocked, so
   the measure cannot be computed task-first — and computing it any other way
   reproduces v1.
4. **No human verification anywhere.** Every classification row, every crosswalk
   row and the rubric are unreviewed.
5. **Granularity unconfirmed.** It is not yet established what PSA publishes
   publicly, at what level, for any of the four metrics. Until that is known,
   even a successful retrieval might not support occupation-level display.

### What would make it ready

A defensible minimum for integration:

1. PSOC 2012 retrieved and the code list verified, including minor and unit
   groups.
2. PSA LFS employment published at whatever granularity PSA actually publishes,
   with reference periods and, where microdata permits, uncertainty.
3. OWS wages, if an occupation table exists, explicitly labelled as
   establishment-sector wages with the wage concept named.
4. SOF published as the distribution of OFWs by major occupation group, with
   the denominator stated.
5. O\*NET retrieved, a reviewed PSOC↔ISCO↔SOC crosswalk, and task statements
   extracted.
6. One exposure run of at least three replicates, with the stability report and
   face-validity review completed.
7. Independent review of the rubric by at least one labour economist, and of the
   classification by at least one Philippine labour statistician.

Items 1–4 alone would make a **real** workforce layer: fewer metrics than v1,
broader occupational groups, visible gaps, and every number traceable. That is
worth integrating. Item 5–7 gate the exposure layer specifically, and the
exposure layer should be integrated last and labelled experimental wherever it
appears.

### A recommendation the brief did not ask for

If Philippine AI Report needs a workforce layer sooner than items 1–7 allow,
integrate the **evidence ledger** rather than the metrics: the PSOC structure,
the metric definitions, the source registry and the honest gap map. It is
publishable today, it is useful — it tells a reader what is knowable about
Philippine occupational data and what is not — and it makes the subsequent
arrival of real figures an improvement rather than a correction.

The one thing not to do is integrate v1's numbers while pointing at v2's
methodology.
