# TrabahoLens

A Philippine labour-market research tool organised around the **Philippine
Standard Occupational Classification (PSOC)**, built so that every figure states
what kind of evidence it is, where it came from, and what period it covers — and
so that a gap in the evidence appears as a gap, not as a number.

> **Research preview — awaiting independent review.** This release carries real
> PSA LFS employment, SOF overseas-worker distributions and OWS wage references,
> plus ILOSTAT tabulations of the Philippine LFS. No synthetic v1 values are
> carried forward. The AI task-exposure layer is an **experimental model
> estimate**: it is not human-reviewed and has had no independent validation.
> Posting demand and informal employment remain unavailable. See
> [`docs/limitations.md`](docs/limitations.md) and
> [`docs/readiness-report.md`](docs/readiness-report.md).

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

Ten layers, all read from `site/data.json`. The interface writes no label set,
count or metric name into its own markup.

| Layer | Source | Resolution | Published |
| --- | --- | --- | --- |
| AI Task Exposure | Model-scored PSA task statements (experimental) | 447 of 466 PSOC unit groups | 894 dimension scores |
| Employment | PSA LFS 2024 | 10 major groups | 10 values |
| Employment Detail | ILOSTAT, ISCO-08 two-digit = PSOC sub-major | 43 sub-major groups | 43 values |
| Earnings (PHP) | ILOSTAT, employees only | 10 major groups | 10 mean, 10 median |
| Wage Rates (OWS) | PSA OWS, source-native job position × industry | not mapped to PSOC | 684 records, 9 withheld |
| Education | ILOSTAT, share with tertiary education | 10 major groups | 10 values |
| Own-Account & Family | ILOSTAT status in employment | 10 major groups | 10 values |
| OFW Distribution | PSA SOF Apr–Sep 2024 | 10 major groups | 9 values; armed forces blank in source |
| Posting Demand | none verified | — | unavailable |
| Informal % | none published by occupation | — | unavailable |

- The official 2022 PSOC workbook's explicit hierarchy, including 466 unit groups.
- A treemap with search, filters, zoom, source details, table view, CSV export,
  keyboard access and light/dark themes. Its look follows
  [karpathy.ai/jobs](https://karpathy.ai/jobs/).
- Every metric the project intends to publish, defined **before** it has a
  value, with the source that would satisfy it, the level that source publishes
  at, the denominator, and the reading it is most often confused with.
- An evidence badge on every metric: Official statistic · Calculated statistic ·
  Estimate · Proxy · Experimental model-derived score.
- Every source and its current state, including the ones that turned out not to
  be used at all.

Missing means missing: an unavailable value is empty with a stated reason, never
zero, a group average or a midpoint.

### Reading the map

- **Area** is employed persons on every layer except two. On Wage Rates every
  box is equal. On AI Task Exposure, area grows with the **cube of the PSA task
  statements listed for the occupation**. That is a display stretch of a real,
  published count so that differences show. It is **not** employment: PSA
  publishes employment only at major group, and the project does not apportion
  it to occupations.
- **Colour** orders the selected layer on a green > amber > red scale, following
  karpathy.ai/jobs. On exposure, green is little task exposure and red is most.
  Colour is not a verdict, and no text next to it frames exposure as risk or
  job loss.

## On AI exposure

> Generative-AI task exposure indicates how much an occupation's tasks may be
> affected or assisted by generative AI. It is not an estimate of automation,
> displacement, layoffs, or future employment.

Two model-scored 0–5 dimensions — technical task exposure and
human-interaction/physical-presence intensity — scored on **task statements**
rather than job titles. Adoption friction is not model-scored; evidence
confidence is derived from provenance. The rubric prohibits combining the
dimensions, because any weighted sum reads as a job-loss probability.

Current run: 447 of 466 unit groups scored from 3,318 of 3,362 PSA task
statements, by `deepseek-v4.1-flash` through NYO, two attempts per task at
temperature 0, raw responses retained. The 19 unit groups with no PSA task list
are shown faint and unscored; no score is borrowed from a neighbour. The harness
refuses to fall back to title-based scoring.

**This is an experimental score. It has not been human-reviewed and has not
undergone independent labour-economist validation.** Multi-model agreement has
been measured (see the [sensitivity report](docs/sensitivity-report.md)); it is
not validation.

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
make test              # validators, scoring harness, reproducibility
make check             # structural and consistency checks
make check-stale       # prove committed artifacts match their inputs
make determinism       # prove two builds are byte-identical
make validate-release  # validate the release manifest and site payload
make browser-qa        # headless Chrome interaction QA (needs the local server)
```

Last full run on this branch: 227 Python tests, 65 of 65 browser QA checks and
5 Node dashboard tests pass, along with `check`, `determinism`, `check-stale`
and `validate-release`. Automated checks do not prove source statistics are
error-free, and they do not establish visual acceptance on real devices.

## Data layout

| Path | Contents |
| --- | --- |
| `data/canonical/` | Normalised PSOC tables: classifications, occupations, metric observations, crosswalk, transformations, model scores |
| `data/sources/` | Source registry and hashed retrieval manifest |
| `data/raw/` | Explicitly allowlisted, unmodified release snapshots; other raw downloads ignored |
| `data/reference/ows_wage_benchmarks.csv` | Source-native wage records, with precision and withheld-row explanations |
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

Visualisation approach and colour scale follow Andrej Karpathy's
[US Job Market Visualizer](https://karpathy.ai/jobs/)
([source](https://github.com/karpathy/jobs)). No data is drawn from it.

## For reviewers

Start with [`docs/readiness-report.md`](docs/readiness-report.md), which lists
the remaining gates. What a reviewer is most needed for:

1. The exposure scores: rubric (`data/exposure/`), method
   ([exposure protocol](docs/exposure-protocol.md)) and results.
2. Whether ILOSTAT's ISCO-08 two-digit tabulation is an acceptable stand-in for
   PSOC sub-major groups (the layers say it is an ILO re-tabulation whose totals
   differ from PSA's by about 2.7%).
3. The exposure map's box-area stretch and the wording around it.
