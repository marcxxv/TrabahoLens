# Remediation review — independent adversarial review of `audit/rebuild-v2`

| | |
| --- | --- |
| Reviewed head | `4af84f6c43407ca1e523e6334e40580375228422` |
| Remediation branch | `audit/rebuild-v2-remediation` |
| v1 baseline | `128dd2238bc3e9657ab84467d0876ffbdf88f494` |

Each finding was reproduced from the code before being accepted. Where the
reviewer's description was incomplete or slightly wrong, that is recorded — a
review is evidence, not instruction.

---

## Verdict summary

| # | Finding | Verdict |
| --- | --- | --- |
| 1 | Retrieval disconnected from metric construction | **Confirmed** (with a mitigation the reviewer missed) |
| 2 | "Only the bytes are missing" is false | **Confirmed** |
| 3 | Evidence classification conflates authority with derivation | **Confirmed** |
| 4 | PSOC version and source inadequate | **Confirmed** |
| 5 | O\*NET release metadata stale/unjustified | **Confirmed** |
| 6 | No operational PSOC–O\*NET task crosswalk | **Confirmed** |
| 7 | Exposure harness can misreport replication | **Confirmed** |
| 8 | "Independent replicates" / randomisation overstated | **Confirmed** |
| 9 | Ordinal aggregation internally inconsistent | **Confirmed** |
| 10 | Adoption friction is unsupported model judgment | **Confirmed** |
| 11 | Evidence confidence should be calculated | **Confirmed** |
| 12 | Additional exposure validation gaps | **Confirmed** |
| 13 | Populated end-to-end fixtures required | **Confirmed** |
| 14 | UI/doc overstatement and `main` links | **Confirmed** |
| 15 | Source-registry quality | **Confirmed** |
| 16 | Release/CI integrity | **Partially confirmed** |
| 17 | Legacy isolation | **Partially confirmed** — entry points were already removed |

---

## 1. Retrieval disconnected from metric construction — CONFIRMED

Reproduced. `build_canonical.build_metric_observations` computed
`retrieved = retrieval.get("status") == "retrieved"` from
`data/sources/source-registry.yaml` — a hand-edited YAML field — and never read
`data/sources/retrieval-manifest.json`. `grep` confirms only `build_release.py`
read the manifest, and only to report attempt state.

No parser existed anywhere in `src/trabaholens/v2/`. The only `parse_*` function
in the package was `score_exposure.parse_response`, which parses a model reply.

The "worse" claim was reproduced directly. Flipping `psa_lfs` to
`status: retrieved` and rebuilding produced ten rows with
`availability=published` and `metric_value=''`, `source_file_hash=''`,
`retrieved_at=''`, `reference_period=''`.

**One correction to the finding.** The reviewer implies this could ship. It
could not: `make validate-release` rejected that state with 40 failures
(`published_without_value`, `provenance`). The defect failed closed. It remains
a real defect — the builder should never construct an invalid state, and the
architectural gap (no manifest consumption, no parsers) is exactly as described
— but the release gate was not bypassable this way.

**Fixed by** the staged pipeline in `v2/pipeline.py`, `v2/acquisition_state.py`
and `v2/sources/`. Publication now requires a verified manifest entry, a
hash-matching file on disk, a successful parse into a normalised source table, a
documented transformation, and complete provenance. The registry is
configuration; the manifest is evidence.

## 2. "Only the bytes are missing" is false — CONFIRMED

The previous branch said acquisition, hashing, manifest and validators were
complete and only source bytes were missing. Parsing, classification
reconciliation, estimation and source-to-observation construction did not exist,
so the claim overstated readiness materially.

**Fixed by** a machine-readable stage model. Every pipeline stage now reports one
of `implemented_verified_with_real_source`, `implemented_fixture_tested_only`,
`designed_not_implemented`, `blocked_by_source_access`,
`blocked_by_unresolved_methodology`, `awaiting_human_review`. The release
manifest carries it, the readiness report renders it, and a test asserts the
docs match.

## 3. Evidence classification conflates authority with derivation — CONFIRMED

The single `estimate_type` axis had `official_statistic` applied to
`employment_count`, `wage_basic_pay`, `ofw_distribution_share` and
`informal_employment_share`. All four are **survey estimates**. PSA publishing
them makes them official; it does not make them directly observed. No
source-authority field existed.

**Fixed by** two independent axes, `derivation_class` and `source_authority`.
No metric is `directly_observed` today, and that is the correct state.

## 4. PSOC version and source inadequate — CONFIRMED

The canonical classification held 10 major and 43 sub-major groups entered from
an ISCO-08 skeleton, marked `unverified_pending_source`. The current PSA
publication is the **2022 Updates to the 2012 PSOC** (10 major, 43 sub-major,
130 minor, 456 unit groups).

`psa.gov.ph` remains unreachable from this environment, so the authoritative
volume could not be retrieved. Per the brief, detailed groups are **not**
transcribed from secondary material. A versioned importer is implemented and
fixture-tested; production rows stay unverified; Phase 2 is **not** complete.

## 5. O\*NET release metadata stale/unjustified — CONFIRMED

The registry pinned release 30.2 with no stated reason while 31.0 is current.
`www.onetcenter.org` is unreachable, so neither could be retrieved or hashed.
The registry now targets **31.0**, states why, and records that no snapshot has
been verified.

## 6. No operational PSOC–O\*NET task crosswalk — CONFIRMED

The only mapping present was v1's SOC-major heuristic, correctly marked
`rejected`. Nothing could carry a PSOC unit to an O\*NET task list.

**Fixed by** a crosswalk pipeline preserving every intermediate classification
(PSOC → ISCO-08 → SOC → O\*NET-SOC), recording basis, cardinality, and machine
and human review status separately, refusing to silently resolve many-to-many
mappings, and emitting a coverage report. Title similarity can only *propose*
candidates.

## 7. Exposure harness can misreport replication — CONFIRMED

Reproduced in `score_exposure.main`: a failed call hit
`except Exception: print(...); continue`, and the run manifest recorded
`"run_count": args.runs` — the **requested** count. One success out of three
attempts produced a score whose provenance claimed three runs. Failed calls were
printed to stdout and never retained.

**Fixed by** a per-attempt record model with attempted/successful/failed counts,
a minimum-successful-replicate gate enforced on the actual successes, retained
failure detail, and validators that count successful responses rather than trust
a declared number.

## 8. "Independent replicates" and randomisation overstated — CONFIRMED

Each task is a separate chat request, so shuffling task order cannot test
within-prompt ordering effects — there is no shared prompt to order. At
temperature 0 repeated calls are a reproducibility check, not independent
samples.

**Fixed by** renaming throughout to repeated scoring attempts / run-to-run
agreement / reproducibility check, and by specifying genuine perturbation
designs separately as future work rather than claiming them.

## 9. Ordinal aggregation internally inconsistent — CONFIRMED

The rubric declared each dimension ordinal; `aggregate_tasks_to_occupation`
computed an arithmetic (and importance-weighted arithmetic) mean across tasks.

**Fixed by** median, IQR, full category distribution, and share above a
predeclared threshold. Any mean retained is labelled an experimental convenience
statistic with a sensitivity comparison.

## 10. Adoption friction is unsupported model judgment — CONFIRMED

Dimension C asked the model to judge Philippine regulation, liability,
connectivity, device access, employer scale and informality with no Philippine
evidence supplied.

**Fixed by the preferred remedy**: removed from model scoring entirely. It is
redefined as a future evidence-based contextual layer and is unpublished.

## 11. Evidence confidence should be calculated — CONFIRMED

Dimension D was model-scored although it is determined by metadata the pipeline
already holds.

**Fixed by** deterministic computation from provenance rules, with the component
reasons published alongside the grade.

## 12. Additional exposure validation gaps — CONFIRMED

`assert_no_prohibited_inputs` checked `set(payload) & PROHIBITED_INPUT_KEYS` —
top-level keys only. A nested dict carrying `ofw_share` would have passed.

**Fixed by** recursive checking plus foreign-key and input validation for task
columns, duplicate ids, unknown PSOC/O\*NET codes, invalid importance, rejected
crosswalks and task-source version consistency.

## 13. Populated end-to-end fixtures required — CONFIRMED

The suite proved validators reject bad input but never proved good input
publishes. On an empty production dataset every check passed trivially.

**Fixed by** a golden fixture exercising manifest → hash → parser → normalised
rows → mapping → transformation → observations → release → payload, plus
mutation fixtures for each failure mode, run by `make test-populated-pipeline`.

## 14. UI and documentation overstatement — CONFIRMED

Confirmed three `blob/main` documentation links in `site/index.html` pointing at
documents that exist only on this branch. Also confirmed the unit-vocabulary
problem: 53 aggregate classification units were presented in a way that reads as
53 occupations.

## 15. Source-registry quality — CONFIRMED

Audited every entry against its primary source. Several entries described
landing pages as datasets and an API directory as a table endpoint. Recorded in
`docs/source-coverage.md`.

## 16. Release and CI integrity — PARTIALLY CONFIRMED

`model_runs: []` was hard-coded — confirmed, now derived from run manifests.
Source states and hashes were already derived from the retrieval manifest rather
than hard-coded, so that part of the finding did not hold. Staleness exclusions
were reassessed and narrowed.

## 17. Legacy isolation — PARTIALLY CONFIRMED

The v1 script entry points had **already** been removed on the reviewed head,
and v1 module `main()` functions already raised. What was missing was a test
proving no production target invokes legacy metric generation or scoring. Added.
