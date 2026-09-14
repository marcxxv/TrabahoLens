# TrabahoLens Development Guide

## Build & Run

```bash
uv sync --all-groups
uv run python scripts/serve.py        # http://127.0.0.1:8000
make help                             # the full v2 pipeline
```

Key targets: `make audit` · `fetch-data` · `build-metrics` · `score-exposure` ·
`sensitivity` · `build-site` · `validate-release` · `test` · `check` ·
`determinism`.

Run `make check && make test && make determinism` before committing. If you
touched a canonical table, run `make build-release` and commit the regenerated
release — CI fails on stale artifacts.

## Architecture

`src/trabaholens/v2/` is the current pipeline. The modules outside it are v1,
retired to inert stubs and kept readable because `docs/audit/baseline-audit.md`
cites them line by line.

| Module | Role |
| --- | --- |
| `v2/schema.py` | Controlled vocabularies, table columns, metric definitions |
| `v2/psoc.py` | PSOC 2012 major and sub-major groups |
| `v2/acquire.py` | Hashed retrieval; records failures as failures |
| `v2/build_canonical.py` | Builds the six canonical tables |
| `v2/build_release.py` | Release manifest and provenance-first site payload |
| `v2/score_exposure.py` | Replicated task-exposure scoring harness |
| `v2/exposure_analysis.py` | Stability and sensitivity report |
| `v2/validate.py` | Release validation |
| `v2/audit_baseline.py` | Profiles the archived v1 data |

## Non-negotiable rules

These are enforced by validators and tests, not convention. See `AGENTS.md` for
the full set and the reasoning.

1. **Never invent a value.** Missing means empty plus an `availability` that
   says why — never zero, a category average, or a midpoint.
2. **PSOC is canonical.** O\*NET and SOC are US-derived proxies and must be
   labelled so.
3. **Provenance travels with the value.** No published number without estimate
   type, source, hash, retrieval date, reference period and granularity.
4. **No hazard framing for exposure.** No risk, job loss, displacement,
   automation probability or "jobs at risk". The validator is negation-aware, so
   the disclaimer is fine; routing around it is not.
5. **No hard-coded counts.** Derive from `site/data.json`.
6. **Scoring is task-first, replicated, provenanced.** No distribution anchor in
   the prompt, no labour-market inputs to the model, at least two runs, raw
   responses retained, history never overwritten.

## Code style

**Python 3.10+, `uv`.** `snake_case` functions and variables, `PascalCase`
classes. Comments explain *why* a constraint exists, usually by naming the v1
defect it prevents — those comments are load-bearing documentation, not noise.
Preserve them.

**Frontend.** Single page, `site/index.html`, vanilla JS and CSS. CSS custom
properties for theming, with a light-mode block. No build step, no framework.
The interface renders only what `data.json` gives it: no label set, count or
metric name is written into the markup.

**Evidence colours are not a hazard ramp.** Hue distinguishes evidence class.
Nothing should read as danger.

## Data

Canonical tables in `data/canonical/`, sources in `data/sources/`, exposure
artifacts in `data/exposure/`, release manifest in `data/release/`.

`data/legacy/v1/` holds the previous dataset verbatim. It is evidence about v1,
never an input to v2 — a test enforces that.
