# TrabahoLens Credibility Rebuild — Implementation Plan (v2)

Branch: `audit/rebuild-v2`
Baseline commit: `128dd2238bc3e9657ab84467d0876ffbdf88f494`
Scope: Phases 1–3 of the credibility rebuild. Phase 4 (Philippine AI Report
integration) is explicitly out of scope. No deployment. No pushes to `main`.

## Operating principle

Accuracy and traceability outrank occupation count, visual impact, feature
completeness, and continuity with current headline figures. Where evidence is
unavailable the metric is marked unavailable or blocked. No value is invented to
keep the interface populated.

## Environment constraint discovered during inspection

Outbound HTTPS from this build environment is restricted by network policy. The
following hosts returned `403` at the egress proxy and could **not** be reached:

| Host | Purpose | Result |
| --- | --- | --- |
| `openstat.psa.gov.ph` | PSA PXWeb API (LFS, OWS) | blocked (403 at proxy) |
| `psa.gov.ph` | PSA publication pages (SOF, PSOC) | blocked (403 at proxy) |
| `www.onetcenter.org` | O*NET 30.2 text database | blocked (403 at proxy) |
| `openrouter.ai` | LLM scoring provider | blocked (403 at proxy) |

`OPENROUTER_API_KEY` is also unset in this environment.

Consequence: primary-source **acquisition** and LLM **scoring runs** cannot be
executed here. This does not change the plan's structure — it changes what the
release may legitimately publish. Every metric whose value depends on a source
that could not be retrieved is published with `availability = blocked_pending_source`
and **no numeric value**. The acquisition and scoring code is written, versioned,
hash-checked and runnable; it is simply not run in this environment. The release
manifest records this explicitly.

This is the outcome the brief anticipates: "If public microdata is not available
or use is restricted: do not fabricate granular estimates... mark finer
occupations unavailable."

## Phase 0 — Forensic baseline

1. `src/trabaholens/v2/audit_baseline.py` profiles every legacy artifact
   programmatically (counts, nulls, duplicates, repeated-value runs, group
   totals, reconciliation, crosswalk cardinality, determinism) and writes
   `docs/audit/current-data-profile.json`.
2. `docs/audit/baseline-audit.md` — narrative audit with code-path attribution
   for every displayed metric, citing file and line.
3. `docs/audit/metric-inventory.csv` — one row per displayed metric with the
   full provenance column set required by the brief.
4. `docs/audit/source-claims.csv` — one row per source claimed anywhere in the
   UI, README, metadata or social-preview text, with the verdict on whether a
   reproducible artifact backs it.

Legacy data is copied to `data/legacy/v1/` before anything is rewritten.

## Phase 1 — Credibility reset

* Remove the hiring-intensity layer entirely (universal placeholder `50`).
* Remove the "monthly payroll", "wages exposed", "OFW-linked jobs" and
  "jobs by exposure" aggregates, all of which multiply synthetic employment.
* Remove category-constant wages, category-constant informal shares and
  PSOC-major OFW shares presented as occupation-level facts.
* Derive every occupation count at build time from the published dataset; no
  hard-coded counts anywhere in markup, metadata or prose.
* Rename "Risk Vector Explainer" → "Task Exposure Explainer"; replace all
  risk/automation/displacement vocabulary.
* Replace the red/amber/green risk ramp with a sequential, non-alarm scale.
* Every published field carries separate visible `derivation_class` and
  `source_authority` badges, each with a plain-language tooltip.
* Fixed, always-visible exposure disclaimer beside the exposure layer.

The treemap's core encoding (tile area ∝ employment) depends on fabricated
occupation-level employment. Because that employment is being withdrawn, the
area encoding is withdrawn with it; the classification view replaces it. This is
a deliberate loss of visual impact in exchange for not asserting false
quantities.

## Phase 2 — Philippine-first foundation

Canonical key becomes PSOC, not SOC/O*NET. Normalised tables under
`data/canonical/`:

* `classifications.csv` — PSOC 2012 hierarchy (major and sub-major groups).
* `occupations.csv` — canonical occupation/aggregate units keyed by `psoc_code`.
* `metric_observations.csv` — long-format observations, one row per
  (occupation, metric, reference period), each carrying source, granularity,
  estimate type, confidence grade and suppression status.
* `crosswalk_psoc_isco_soc.csv` — explicit PSOC↔ISCO↔SOC mappings with
  `match_type`, `match_quality`, `mapping_basis` and `review_status`.
* `transformations.csv` — every transformation applied, by id.
* `model_scores.csv` — released exposure scores with full model provenance.

Source governance: `data/sources/source-registry.yaml` and
`data/sources/retrieval-manifest.json`. `src/trabaholens/v2/acquire.py` performs
hashed, manifest-recording retrieval; it fails loudly rather than silently
degrading when a host is unreachable. Licensing separated per source in
`docs/data-licenses.md`; the repository's MIT licence is scoped to code only.

The PSOC code list itself is entered from classification documentation because
the authoritative PSA volume could not be retrieved here. Every such row is
marked `verification_status = unverified_pending_source` and a validator fails
the release if an unverified row is published without that marker.

## Phase 3 — Generative-AI task exposure

* Versioned rubric `data/exposure/rubric/rubric-v0.2.0.yaml`, with separate
  ordinal dimensions for technical task exposure and human-interaction or
  physical-presence intensity. Adoption friction is removed; evidence
  confidence is computed from provenance. Nothing is combined into a job-loss number.
* Versioned prompt `data/exposure/prompts/prompt-v0.2.0.md`. The legacy
  prompt's "Expected average: ~3.5–4.5" line is removed — it anchored the score
  distribution. Employment, wages, OFW share and informality are removed from
  the scoring context; they are not evidence of technical task exposure.
* `src/trabaholens/v2/score_exposure.py` runs repeated scoring attempts,
  records provider/model/snapshot/temperature/date, saves
  raw responses under `data/exposure/runs/<run_id>/`, aggregates by median,
  retains disagreement and reports stability. Reruns write new run directories;
  historical results are never overwritten.
* `src/trabaholens/v2/exposure_analysis.py` produces the stability and
  sensitivity report.

Because scoring cannot run here, `model_scores.csv` ships empty (header only)
and the UI shows exposure as unavailable rather than showing legacy scores.
Legacy scores remain readable under `data/legacy/v1/` and are never re-published.

## Validation

`src/trabaholens/v2/validate.py` + `tests/` enforce, as hard failures:

1. No placeholder constants (notably a universal `50`) in published data.
2. No proxy or estimate labelled as an official statistic.
3. No occupation-level value sourced from a broader granularity without an
   explicit `source_granularity != display_granularity` disclosure.
4. No model-derived score without model id and prompt version.
5. No aggregate published alongside its own components (double counting).
6. No "risk", "jobs at risk", "at risk", "replaceable", "automation
   probability" or "displacement" language in the site or published data.
7. No hard-coded occupation counts in the site.
8. No missing value backfilled with zero or a neutral midpoint.
9. Deterministic rebuild: two builds byte-identical apart from declared
   timestamps.
10. No stale generated artifacts relative to their inputs.

## Pipeline

`make audit | fetch-data | validate-raw | build-crosswalk | build-metrics |
score-exposure | validate-release | build-site | test | check`.

## Deliverables

Baseline audit, source registry, metric inventory, data dictionary,
methodology, limitations, licensing, PSOC-first schema, crosswalk + review
report, acquisition pipeline, validation suite, exposure protocol, sensitivity
report, revised interface, release manifest, migration notes, readiness report.
