# Contributing to TrabahoLens

TrabahoLens is a research tool whose value rests entirely on whether its figures
can be traced. A contribution that improves the interface but weakens
traceability is a regression here.

## Setup

```bash
uv sync --all-groups
make help
```

## Before opening a pull request

```bash
make check        # compile + release validation
make test         # the suite
make determinism  # two builds byte-identical
```

If you changed a canonical table, run `make build-release` and commit the
regenerated release. CI fails on stale artifacts.

## The rules that will block a pull request

These are enforced by validators and tests. Full reasoning in `AGENTS.md`;
each traces to a specific defect in the previous version.

1. **No invented values.** If evidence is unavailable, the metric is marked
   unavailable. Do not fill a gap with zero, a category average, a neighbour's
   figure, or a midpoint. Do not split a group total across finer occupations by
   any weighting scheme.
2. **Provenance with every number.** `estimate_type`, `availability`,
   `confidence_grade`, `source_id`, `source_url`, `source_file_hash`,
   `retrieved_at`, `reference_period`, and both granularity fields.
3. **Registered sources only.** Add to `data/sources/source-registry.yaml`
   first, with universe, exclusions, reference period, licensing and
   attribution. A metric citing an unregistered source fails validation.
4. **No hazard framing for exposure.** No risk, job loss, displacement or
   automation probability.
5. **No hard-coded counts.** Derive them from the payload.
6. **PSOC codes must be verified or marked unverified.** Do not add codes you
   have not checked against the PSA volume.

## Adding a metric

1. Add a `MetricDefinition` in `v2/schema.py` — including its denominator and
   the reading it is most often confused with. Both are required fields, and
   both end up in the interface.
2. Register the source, if it is new.
3. Rebuild: `make build-metrics && make build-site`.
4. Add a test that the check protecting it **fires on a violating fixture**.
   Tests that only confirm valid data passes are close to worthless here — the
   released dataset is currently empty, so everything passes trivially.

## Changing the exposure rubric or prompt

Bump the version and add a new file. Do not edit in place: published scores
reference their version, and rewriting a version silently invalidates them.

The prompt must not state an expected average or distribution — the harness
refuses to run if it detects one. Disabling that guard is not an acceptable fix
for a failing build.

## Reporting a data problem

Open an issue with the `psoc_code`, the `metric_id`, what is shown, what you
believe is correct, and the source table supporting it. A correction without a
source cannot be applied, however plausible.

## What we will not merge

- A metric without provenance.
- A source citation without retrieval code or a documented manual acquisition.
- Any value derived from `data/legacy/v1/`.
- Reintroduction of a hiring-intensity field without real job-posting data.
- Claims of expert validation that did not occur.
