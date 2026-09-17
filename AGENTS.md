# Guidance for AI agents working on TrabahoLens

This repository was rebuilt after an audit found that none of its published
numeric fields was an observed statistic. The rules below exist to stop that
recurring. They are not style preferences.

## The first rule

**Never create a value to fill an interface.** If evidence is unavailable, mark
the metric unavailable or blocked. A visible gap is information. A plausible
number with no source is a fabrication, whatever the intent behind it.

Corollaries:

- Do not fill a missing value with zero, a category average, a neighbouring
  occupation's figure, or a neutral midpoint.
- Do not distribute a group total across finer occupations by any weighting
  scheme. This is exactly how v1's employment figures were produced.
- Do not broadcast a category constant across the occupations in it.
- Do not widen a dataset because the visualisation looks sparse.

## Language

Generative-AI task exposure must never be described as, or implied to be:
automation probability, replacement probability, displacement, layoffs,
unemployment, job-loss risk, occupational decline, or future employment change.

Use task-exposure terminology. A validator enforces this over `site/index.html`
and `site/data.json`, and will fail the build. It is negation-aware, so the
required disclaimer is permitted; do not try to route around it.

When presenting a model's output, write "the scoring model judged" or "the task
profile suggests". A model's rationale is not a finding.

## Provenance

Every published numeric value carries `derivation_class`, `source_authority`, `availability`,
`confidence_grade`, `source_id`, `source_url`, `source_file_hash`,
`retrieved_at`, `reference_period`, `source_granularity` and
`display_granularity`. A value cannot be added without them; validation rejects
it.

A value from a broader source shown at a finer level is a **proxy**, graded
down, with the mismatch displayed. It is never an official statistic.

## Classification

PSOC is canonical. O\*NET and SOC are US-derived proxies and must be labelled
so. Never map occupations on English title similarity — a mapping with
`mapping_basis = title_similarity_only` must be `review_status = rejected`, and
observations may not resolve through a rejected crosswalk.

Do not add PSOC codes you have not verified against the PSA volume. If you must
add unverified rows, mark them `unverified_pending_source`.

## Scoring

If you change the exposure prompt or rubric, bump the version and add a new file
rather than editing in place. Published scores reference their version.

The prompt must not state an expected average, median, spread or distribution
shape. The harness refuses to run if it detects one — that guard is deliberate,
and disabling it is not an acceptable fix.

The scorer must not receive employment, wages, OFW share or informality. These
are not evidence of what a model can do with a task. The harness refuses to send
them.

Runs need at least two successful repeated attempts. Disagreement is published, not smoothed.
Reruns write new directories; historical runs are never overwritten.

## Before you commit

```bash
make check            # compile + release validation
make test             # the suite
make determinism      # two builds byte-identical
```

If you changed a canonical table, run `make build-release` and commit the
regenerated release; CI fails on stale artifacts.

## What not to do

- Do not run the retired v1 modules. They raise on purpose.
- Do not read `data/legacy/v1/` from any v2 module. A test enforces this.
- Do not reintroduce a hiring-intensity field without real posting data, and
  then only as a posting or platform demand signal.
- Do not hard-code an occupation count anywhere. Derive it from the payload.
- Do not claim external expert validation that did not occur.
