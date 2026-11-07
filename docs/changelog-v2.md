# Changelog — v2 credibility rebuild

Branch `audit/rebuild-v2`, from `128dd2238bc3e9657ab84467d0876ffbdf88f494`.

Phases 1–3 of the rebuild. Phase 4 (Philippine AI Report integration) is out of
scope. Not deployed. Not merged to `main`.

---

## Removed

Each removal is evidenced in [`audit/baseline-audit.md`](audit/baseline-audit.md)
and reproducible from `make audit`.

### Metrics

- **Employment (`jobs`).** A hard-coded total per PSOC major group split across
  occupations by English title keyword. 173 rows carried 43 distinct values;
  150 rows shared a value with another row; 39 shared exactly 100,851.
- **Wages (`pay`).** A constant per internal category. 11 distinct values across
  173 occupations.
- **Hiring intensity (`outlook`).** The literal integer `50` on every row,
  attributed in the interface to PhilJobNet and IBPAP, neither of which the
  repository ever touched. Removed with all seven derived statistics.
- **Informal share.** A constant per internal category. 10 distinct values.
- **OFW share.** Nine constants per PSOC major group that sum to 1.02 —
  P(occupation | OFW) published as P(OFW | occupation).
- **Exposure score (0–10).** A single unreplicated model run under a prompt
  stating `Expected average: ~3.5-4.5`, conditioned on the synthetic values
  above, with no model identifier recorded.

### Derived headlines

Total jobs (49M) · monthly payroll · wages exposed · OFW-linked jobs ·
domestic jobs · jobs by exposure · jobs by intensity · intensity tiers ·
high- and low-intensity jobs.

Each multiplied or summed values that were not measurements.

### Source citations

PSA LFS, PSA OWS, PSA SOF, PhilJobNet, IBPAP and POEA were cited in the
interface and README with no retrieval code, data file or URL behind them. Six
of seven cited sources were unsupported; only O\*NET was real.

### Interface elements

"Risk Vector Explainer" · risk vectors · the green→amber→**red** hazard ramp ·
the hard-coded "173 occupations" in README and `og:description` · the treemap.

The treemap went because its core encoding was tile area ∝ employment, and that
employment was synthetic. Keeping the picture would have kept the claim.

---

## Added

### Phase 0 — forensic baseline

`docs/audit/baseline-audit.md` · `metric-inventory.csv` (22 provenance columns
× 14 metrics) · `source-claims.csv` · `current-data-profile.json`, regenerated
by `make audit` so every number in the audit is re-derivable.

`data/legacy/v1/` — the v1 artifacts, verbatim, hash-verified before the
originals were moved.

### Phase 1 — credibility reset

Interface rebuilt around evidence:

- Five evidence classes, each shown as a badge with a plain-language tooltip,
  drawn from the data rather than chosen in markup.
- The required exposure disclaimer, fixed beside the exposure layer, always
  rendered.
- All counts derived from `data.json` at runtime.
- Colour encodes evidence class, not alarm.
- A metric ledger stating, per metric, the source that would satisfy it, the
  granularity that source publishes at, the denominator, and the reading it is
  most often confused with.
- A source table showing every source's state and why.

`docs/methodology.md` · `data-dictionary.md` · `limitations.md` ·
`changelog-v2.md` · `data-licenses.md` · `migration-notes.md` ·
`exposure-protocol.md` · `readiness-report.md`.

### Phase 2 — Philippine-first foundation

- PSOC 2012 canonical: 10 major groups (including 0, absent from v1) and 43
  sub-major groups. Minor and unit groups deliberately absent.
- Six normalised tables under `data/canonical/`.
- Six metric definitions written before any value exists, each naming its
  required source, expected granularity, denominator and common misreading.
- `data/sources/source-registry.yaml` — 15 sources with universe, exclusions,
  reference period, classification version, licensing and attribution recorded
  separately per source.
- `data/sources/retrieval-manifest.json` — hashed, timestamped attempts.
- `v2/acquire.py` — retrieval with SHA-256; failures recorded, never swallowed.
- Explicit crosswalk with match type, quality, basis, review status and derived
  cardinality flags. v1's SOC heuristic preserved as `rejected`.

### Phase 3 — task-exposure layer

- `rubric-v0.1.0.yaml` — four independent 0–5 dimensions. Combining them is
  prohibited by the rubric itself.
- `prompt-v0.1.0.md` — task-level, no distribution anchor, no labour-market
  inputs, with a table of every change from v1 and why.
- `v2/score_exposure.py` — ≥2 replicates, randomised task order, all raw
  responses retained, new run directory per invocation, median with retained
  disagreement. Two guards are runtime refusals, not comments.
- `v2/exposure_analysis.py` — stability, cross-model agreement, weighting and
  crosswalk sensitivity, plus a face-validity watchlist.

### Validation and pipeline

`v2/validate.py`; `Makefile`; GitHub Actions CI that fails on stale artifacts
and non-deterministic builds; a test suite.

Every validator is tested against a fixture that **violates** it. The released
dataset is empty, so validating it alone would prove nothing.

---

## Changed

- Canonical key: `ONET-<SOC>` → `PSOC-<code>`.
- `site/data.json`: flat array of 173 records → provenance-first object.
- `make check`: compared 173 titles across three files → runs the release
  validator.
- v1 modules retired to inert stubs; logic preserved as `_v1_main()` because the
  audit cites it line by line.
- `pyproject.toml`: added `pyyaml`, a `dev` group with `pytest`, and pytest
  configuration.

---

## Known state of this release

**Ten LFS employment estimates are published.** PSA matrix 1B3FEMP4 and O*NET
31.0 were retrieved and hash-verified. Only the 2024 annual LFS major-group
values pass all publication gates; O*NET remains blocked by the absent reviewed
crosswalk.

**No exposure score is published.** Task evidence is present, but the harness
still requires an accepted PSOC-to-O*NET mapping and a completed repeated model
run. The v1 scores are not carried forward.

**The PSOC list is unverified.** Entered from ISCO-08-aligned documentation;
every row marked `unverified_pending_source`.

This is the intended outcome under the operating principle. See
[`readiness-report.md`](readiness-report.md) for a component-by-component
assessment.

## 2026-11-07: ILOSTAT layers

Four ILOSTAT SDMX extracts (Philippines, annual 2024, both sexes) are registered,
fetched, hash-verified and parsed: employment by sub-major group, mean and
median monthly earnings of employees, and the education profile. Each is an ILO
re-tabulation of the Philippine LFS and is labelled so. Structural ISCO-08 links
for the 10 major and 43 sub-major groups are marked `source_verified` only when
the code appears in the verified file. Informal employment by occupation remains
unavailable: no Philippine series exists in ILOSTAT or PSA.
