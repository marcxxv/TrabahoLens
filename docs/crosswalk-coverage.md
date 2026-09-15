# Crosswalk coverage report

Required by finding 6. Regenerate with `make build-crosswalk`.

## Status: no operational PSOC–O\*NET chain exists

The composer is implemented and fixture-tested. **No published correspondence
has been retrieved**, so no real chain has been built and
`data/canonical/crosswalk_psoc_isco_soc.csv` contains no PSOC→O\*NET row. A test
asserts that absence, so a chain cannot appear without the correspondences that
justify it.

| PSOC units | High-quality mappings | Ambiguous | Unmatched | Excluded from scoring |
| --- | --- | --- | --- | --- |
| 53 (aggregate only) | 0 | 0 | 53 | 53 |

Coverage share, high quality: **0.0**.

## The path, and why every intermediate is kept

```
PSOC ──published correspondence──▶ ISCO-08
ISCO-08 ──published correspondence──▶ US SOC
US SOC ──structural──▶ O*NET-SOC
```

Each hop carries its own match type, quality, basis and review status, and the
composed edge takes the **worst** of them. `intermediate_codes` records the path
taken, so a reviewer can see which hop lost the quality rather than being handed
a single degraded verdict.

## Rules enforced in code, not by convention

| Rule | Where |
| --- | --- |
| A chain is only as good as its weakest hop | `ComposedMapping.match_quality` |
| A one-to-many hop is never silently resolved | `compose` marks every branch `ambiguous` |
| `no_defensible_match` ends the chain | `CrosswalkEdge.usable` |
| Title similarity may propose, never publish | `UNPUBLISHABLE_BASES`, plus the release validator |
| A rejected hop rejects the chain | `ComposedMapping.review_status` |
| Machine and human review are separate states | `machine_proposed` vs `human_reviewed` |
| An ambiguous or unresolved occupation is not scored | `coverage_report` → `excluded_from_exposure_scoring` |
| Crosswalk uncertainty reaches the score | feeds `compute_evidence_confidence` |

## Correspondences needed

| Hop | Source | State |
| --- | --- | --- |
| PSOC ↔ ISCO-08 | PSA PSOC volume, which documents its ISCO-08 basis | **not retrieved** |
| ISCO-08 ↔ US SOC | Published ISCO/SOC correspondence | **not retrieved** |
| US SOC ↔ O\*NET-SOC | O\*NET distribution | **not retrieved** |

The current canonical table carries a PSOC↔ISCO-08 correspondence at major and
sub-major level marked `structural_derivation` / `machine_proposed`, on the
basis that PSOC 2012 is built on ISCO-08. That is an assumption about structure,
not a retrieved correspondence, and it has not been human-reviewed.

## Philippine-specific occupations: the expected hard case

Kasambahay, tricycle and jeepney driving, street vending, fisherfolk and
barangay health work have no close O\*NET analogue. When the correspondences
arrive these are expected to land in `unmatched` or `ambiguous`, and the correct
outcome is that they are **not scored** — not that a loose match is accepted to
improve coverage. A confident exposure score for kasambahay derived from a US
task profile would be a crosswalk failure presented as a finding.

v1's approach here is instructive: it mapped ten hand-written Philippine
categories alongside US O\*NET occupations describing the same workers, with no
mapping metadata at all. That mapping is preserved in the canonical crosswalk
with `review_status = rejected`.
