# TrabahoLens

A Philippine labour-market research tool organised around the **Philippine
Standard Occupational Classification (PSOC)**, built so that every figure states
what kind of evidence it is, where it came from, and what period it covers — and
so that a gap in the evidence appears as a gap, not as a number.

> **This release publishes no metric values.** The structure, source registry,
> validation rules and interface are complete; the data is not, because no
> source could be retrieved from the build environment. See
> [`docs/limitations.md`](docs/limitations.md). Numbers were not carried over
> from the previous version to fill the space.

## Why this version exists

The previous version of TrabahoLens showed 173 occupations with employment,
wage, informality, overseas-worker, hiring and AI-exposure figures. A forensic
audit established that **none of its published numeric fields was an observed
Philippine statistic**:

- Employment was a hard-coded total per occupational group, split across
  occupations by matching English words in job titles. 173 rows carried 43
  distinct values; 39 occupations shared the identical figure 100,851.
- Wages and informality were constants assigned per internal category — 11 and
  10 distinct values respectively, across 173 occupations.
- Hiring intensity was the literal number `50` on every row, credited in the
  interface to PhilJobNet and IBPAP, neither of which the code ever touched.
- "OFW share" was the wrong conditional probability: the distribution of
  overseas workers *across* occupation groups, published as the share of an
  occupation's workers who are overseas. The nine constants sum to 1.02.
- The AI exposure score came from a single unreplicated model run under a prompt
  that told the model its expected average, conditioned on the synthetic figures
  above, with no record of which model produced it.

Full evidence: [`docs/audit/baseline-audit.md`](docs/audit/baseline-audit.md),
reproducible with `make audit`.

Those metrics are withdrawn rather than relabelled. Relabelling a value that was
never measured still publishes it.

## What it shows now

- The PSOC 2012 structure — 10 major groups and 43 sub-major groups.
- Every metric the project intends to publish, defined **before** it has a
  value, with the source that would satisfy it, the level that source publishes
  at, the denominator, and the reading it is most often confused with.
- An evidence badge on every metric: Official statistic · Calculated statistic ·
  Estimate · Proxy · Experimental model-derived score.
- Every source and its current state, including the ones that turned out not to
  be used at all.

## On AI exposure

> Generative-AI task exposure indicates how much an occupation's tasks may be
> affected or assisted by generative AI. It is not an estimate of automation,
> displacement, layoffs, or future employment.

The measure is rebuilt as four independent 0–5 dimensions — technical task
exposure, human-interaction and physical-presence intensity, adoption friction,
and evidence confidence — scored on **task statements** rather than job titles.
The rubric prohibits combining them, because any weighted sum reads as a
job-loss probability.

No score is published in this release: the scoring harness requires task
evidence that could not be retrieved, and refuses to fall back to title-based
scoring. **This experimental score has not yet undergone independent
labour-economist validation.**

## Quickstart

```bash
uv sync --all-groups
uv run python scripts/serve.py     # http://127.0.0.1:8000
```

## Pipeline

```bash
make help              # all targets

make audit             # profile the archived v1 dataset
make fetch-data        # attempt every registered source, hash it, record the outcome
make build-metrics     # rebuild the canonical PSOC tables
make score-exposure MODEL=<provider/model-id>
make sensitivity       # stability and sensitivity report
make build-site        # release manifest + site payload, then validate
make test              # 67 tests
make determinism       # prove two builds are byte-identical
```

## Data layout

| Path | Contents |
| --- | --- |
| `data/canonical/` | Normalised PSOC tables: classifications, occupations, metric observations, crosswalk, transformations, model scores |
| `data/sources/` | Source registry and hashed retrieval manifest |
| `data/exposure/` | Versioned rubric, versioned prompt, scoring runs |
| `data/release/` | Release manifest |
| `data/legacy/v1/` | The previous dataset, verbatim. Evidence about v1, never an input to v2 |
| `site/data.json` | Provenance-first payload the interface reads |

## Documentation

| Document | For |
| --- | --- |
| [Methodology](docs/methodology.md) | How the data model, sources, crosswalks and exposure measure work |
| [Data dictionary](docs/data-dictionary.md) | Every field, every controlled vocabulary |
| [Limitations](docs/limitations.md) | What is missing, what will stay missing, and weaknesses in the rebuild itself |
| [Baseline audit](docs/audit/baseline-audit.md) | What the previous version actually published |
| [Exposure protocol](docs/exposure-protocol.md) | How to run and report a scoring run |
| [Sensitivity report](docs/sensitivity-report.md) | Stability and sensitivity analysis |
| [Data licensing](docs/data-licenses.md) | Per-source terms and attribution |
| [Migration notes](docs/migration-notes.md) | v1 → v2 field and command mapping |
| [Readiness report](docs/readiness-report.md) | Component-by-component integration assessment |
| [Changelog](docs/changelog-v2.md) | What changed in this rebuild |

## Licensing

The MIT licence covers the **code in this repository only**. It does not grant
rights over PSA statistics, O\*NET data, or any other source. Terms are recorded
per source in [`docs/data-licenses.md`](docs/data-licenses.md).

O\*NET is a US Department of Labor product used under CC BY 4.0, and is a
US-derived proxy for any Philippine occupation.

## Credits

Visualisation approach inspired by [karpathy.ai/jobs](https://karpathy.ai/jobs/).
No data is drawn from it.
