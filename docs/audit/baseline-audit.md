# TrabahoLens v1 — Forensic Baseline Audit

| | |
| --- | --- |
| Repository | `marcxxv/TrabahoLens` |
| Audited commit | `128dd2238bc3e9657ab84467d0876ffbdf88f494` |
| Audit branch | `audit/rebuild-v2` |
| Machine-readable profile | [`current-data-profile.json`](current-data-profile.json) |
| Regenerate with | `make audit` (`uv run python scripts/audit_baseline.py`) |
| Frozen inputs | [`data/legacy/v1/`](../../data/legacy/v1/) |

Every quantitative claim below is emitted by `src/trabaholens/v2/audit_baseline.py`
into `current-data-profile.json`. Nothing here is asserted from memory of the
code; each finding names the file and line that produces the value.

> **Note on method.** `uv run python scripts/check.py` passes on the audited
> commit. It verifies only that the CSV, the score cache and `site/data.json`
> contain the same 173 titles. It does not test whether any value is true. A
> green build was not treated as evidence of validity.

---

## 1. Record counts

| Artifact | Records |
| --- | --- |
| `data/reference/occupations_seed.json` (curated input) | 44 |
| `data/derived/occupations_ph.csv` (derived table) | 173 |
| `data/derived/scores_ai_only.json` (score cache) | 173 |
| `site/data.json` (published) | 173 |

Three intermediates — `onet_occupations.json`, `ph_occupations_v2.json`,
`ph_occupations_v2_with_stats.json` — sit between the seed and the CSV and are
listed in `.gitignore`. They are not committed, so a clean checkout cannot
regenerate the published dataset without re-downloading O\*NET.

**Occupation-count claim.** The public claim is 173, in `README.md:3` and in the
OpenGraph description at `site/index.html:12`. Both are hard-coded string
literals. A search of the full history (`git log --all -S"500+ occupations"`,
plus a regex sweep of every blob for a 500-class count) found **no 500+ claim
anywhere in this repository**. The audit brief's hypothesis of a "500+ vs 173"
discrepancy is **not confirmed inside this repository**; if such a claim exists
it lives in an external surface (site copy, social post, or the Philippine AI
Report) that is outside this repo and must be corrected there. The defect that
*is* confirmed is different and still real: the count is hard-coded in two
places rather than derived, so it silently goes stale whenever the dataset
changes.

Of the 44 curated seed occupations, **8 survive** into the published dataset by
title. The other 36 — including `bpo and call center agents`, `accountants`,
`civil engineers`, `data encoding clerks` — were dropped when the pipeline
switched to selecting US O\*NET titles. The most Philippine-relevant records in
the repository were discarded in favour of US occupational granularity.

---

## 2. Where the pipeline actually starts

```
fetch_onet.py            downloads O*NET 30.2 (US SOC) ─ 1 016 US occupations
  └─ filter_ph_occupations.py   keeps a keyword-ranked quota per PSOC major group
       └─ assign_ph_stats.py    attaches PH statistics
            └─ make_csv_ph.py   flattens to occupations_ph.csv
                 └─ score_ai_only.py   one LLM call per row
                      └─ build_site_data.py   writes site/data.json
```

The canonical identifier is `ONET-<SOC code>` (`pipeline_utils.make_onet_id`).
PSOC is attached afterwards as a label. **Hypothesis confirmed: the dataset is
US-first with a Philippine label applied downstream.**

`filter_ph_occupations.GROUP_LIMITS` sets a fixed quota per PSOC major group
(12/55/18/12/20/15/18/15) and `KEYWORD_BONUSES` (lines 48–88) ranks candidates by
English keyword. The Philippine occupational structure never determines which
occupations exist; a hand-tuned keyword score does.

### 2.1 The SOC→PSOC mapping

`pipeline_utils.SOC_TO_PSOC_MAJOR` (lines 42–65) maps 22 US SOC 2-digit majors
onto PSOC major groups. It is a bare `dict[str, int]`. There is **no crosswalk
table, no `match_type`, no `match_quality`, no `mapping_basis`, and no
`review_status`** — all four fields the brief requires are absent.

It is aggressively many-to-one:

| PSOC major | US SOC majors collapsed into it |
| --- | --- |
| 2 Professionals | 13, 15, 17, 19, 21, 23, 25, 27, 29 (nine) |
| 3 Technicians | 31, 33, 39, 41 |
| 5 Service and Sales | 35, 37 |
| 7 Craft and Related Trades | 47, 49 |
| 8 Plant and Machine Operators | 51, 53 |

PSOC major group **9 (Elementary Occupations)** is unreachable from any SOC
major. It is the largest group in the real Philippine labour force, and in v1 it
contains exactly three records — all hand-written. PSOC major group **0 (Armed
Forces Occupations)** does not exist in v1 at all.

---

## 3. Metric-by-metric findings

### 3.1 Employment (`jobs`) — fabricated

Produced by `assign_ph_stats.allocate_group_employment` (lines 58–127).

1. `GROUP_TOTALS` (lines 28–38) hard-codes an employment total per PSOC major
   group. There is no source, no reference period and no citation for these nine
   numbers.
2. Any occupation whose title matches a seed record inherits the seed's manually
   written `employment_estimate`.
3. The remainder of the group budget is split across the other occupations in
   proportion to `pipeline_utils.TITLE_SIZE_MULTIPLIERS` (lines 84–99) — regex
   matches on English words, e.g. `\bregistered nurses?\b → 3.0`,
   `\bteachers?\b → 2.2`, `\bdrivers?\b → 1.8` — multiplied by further inline
   keyword boosts at lines 100–112.

**Hypothesis confirmed, and worse than stated.** The published dataset contains
173 rows but only **43 distinct employment values**. **150 of 173 rows (86.7%)
share an employment value with at least one other row**, because occupations
that match no keyword all receive an identical equal split of the residual
budget.

| Repeated value | Occupations sharing it |
| --- | --- |
| 100 851 | 39 |
| 173 913 | 16 |
| 45 842 | 13 |
| 227 642 | 11 |
| 93 023 | 9 |

The 39-way cluster is the clearest illustration. Thirty-three of those rows are
US postsecondary teaching specialisations — *Agricultural Sciences Teachers,
Postsecondary*; *Anthropology and Archeology Teachers, Postsecondary*;
*Area, Ethnic, and Cultural Studies Teachers, Postsecondary* — each credited
with exactly 100 851 Philippine workers. Together they absorb **3 328 083 jobs,
60.5% of the entire PSOC 2 (Professionals) budget**. A further 19 US-style
"First-Line Supervisors of …" rows absorb 3 845 415 jobs.

`7 173 498` of the 49 million published jobs — 14.6% of the published total —
sit on these two US-shaped title families alone.

**Reconciliation.** Eight of nine groups reconcile to `GROUP_TOTALS` exactly —
because the allocator is constructed to force that. PSOC 9 does not: it publishes
8 800 000 against a declared 10 500 000, a 1 700 000 shortfall, because the group
contains only three hand-written records and two of them carry fixed seed values
that stop the residual from being distributed. The published total is 49 000 000
against a hard-coded 50 700 000.

### 3.2 Wages (`pay`) — category constants

`pipeline_utils.wage_for_occupation` (lines 300–341) returns a literal per
category. 173 occupations carry **11 distinct wages**; a single value (₱28 000)
covers 28.9% of rows. Every Legal occupation is ₱45 000; every Agricultural
occupation is ₱12 000. These are not observations of any occupation.

`fetch_psa.py` targets PSA table `0031B3E1030.px`, which is
**`ows_wage_by_industry`** — wages by *industry*, not by occupation. Even if the
fetch were wired in, it could not produce an occupation-level wage.

### 3.3 Hiring intensity (`outlook`) — universal placeholder

`assign_ph_stats.build_stats` line 155 writes the integer literal `50` for every
record. **The profile confirms one distinct value across all 173 rows.**

It is published as a first-class UI layer, described at `site/index.html:1229` as
"Hiring intensity based on PhilJobNet and IBPAP postings (0–100)" and at line
2292 as "0–100, based on PhilJobNet postings". Four derived statistics are built
on it — average hiring intensity, a jobs-by-intensity histogram, intensity tiers,
intensity by pay, intensity by education, "high-intensity jobs" and
"low-intensity jobs". All are arithmetic on the constant 50.

**No PhilJobNet or IBPAP code, data file, URL or retrieval step exists anywhere
in the repository.**

### 3.4 Informal share — category constants

`pipeline_utils.INFORMAL_SHARE_BY_CATEGORY` (lines 122–145). 10 distinct values
across 173 rows; one value covers 33% of rows. No source, no reference period.

### 3.5 OFW share — the wrong conditional probability

`pipeline_utils.PSOC_OFW_SHARE` (lines 67–77) assigns one constant per PSOC major
group, displayed per occupation and labelled "Share of PSOC group working
overseas (PSA SOF 2024)" at `site/index.html:1230`.

The profiler tests the denominator directly. The nine group constants are
0.01, 0.06, 0.04, 0.02, 0.13, 0.02, 0.15, 0.15, 0.44 — and they **sum to 1.02**.

A set of genuine "share of this group's workers who are OFWs" ratios has no
reason to sum to 1. A set that sums to 1 is a *distribution across groups*. So
these numbers are P(occupation | OFW) — how OFWs are distributed across
occupation groups — published as P(OFW | occupation), the share of an
occupation's workers who are overseas. **These are different quantities and the
published label is wrong.** This is the exact error the brief flags as mandatory
to fix, and it is now demonstrable from the shipped data rather than inferred.

Two UI statistics compound it: "OFW-linked jobs" multiplies synthetic employment
by this mislabelled ratio, and "Domestic jobs" subtracts the result from the
synthetic total.

### 3.6 Education — the one traceable metric

`fetch_onet.parse_job_zones` genuinely parses O\*NET Job Zones from the
downloaded database. The value is real, reproducible from a citable source, and
correctly attributed to O\*NET at `site/index.html:1228`.

Two defects remain. It is a **US** construct describing US entry requirements,
presented without a proxy label. And the ten hand-written Philippine records get
`education_code = 3` by default (`filter_ph_occupations.py:156`) when no seed
record matches — a silent midpoint fill.

### 3.7 AI exposure — single unreplicated run, anchored prompt

`score_ai_only.py`. Findings:

- **One run per occupation.** `temperature=0.2`, no seed, no replication, no
  stability measure.
- **Raw responses are discarded.** Only the parsed integer, the rationale string
  and a vector label are kept.
- **Zero provenance.** All eleven required provenance fields are absent from
  every record: `rubric_version`, `prompt_version`, `model_provider`, `model_id`,
  `scoring_date`, `temperature`, `run_count`, `aggregation_method`,
  `uncertainty_or_stability`, `human_review_status`, `raw_response_reference`.
  The cache stores `{title, exposure, rationale, primary_risk_vector}` and
  nothing else. The model that produced the shipped scores is unrecorded.
- **The prompt anchors its own output distribution.** Line 64:
  `Expected average: ~3.5-4.5 (lower than current conflated baseline of 4.5-5.0).`
  This instructs the model toward a target mean before it has seen the
  occupation. Any resulting distribution is partly an artifact of the
  instruction.
- **Synthetic inputs are fed in as causal evidence.** The user message
  (lines 274–284) supplies `employment_estimate`, `avg_monthly_wage_php`,
  `ofw_share` and `informal_share` — all synthetic per §3.1–3.5 — and the system
  prompt tells the model to reason from them: *"High ofw_share means LLM adoption
  at destination may happen faster"*, *"High informality slows LLM adoption"*.
  Fabricated numbers are conditioning a score that is then displayed as evidence
  about those same occupations.
- **Title-only, not task-based.** No O\*NET task statements reach the model; it
  sees a title, a category, a description and the synthetic statistics.
- Scoring is **not** conditioned on employment magnitude in a way that would be
  defensible either — technical task exposure and labour-market context are
  merged into one number.

### 3.8 Row-level provenance

`site/data.json` has fifteen fields per record. **None** is a source, URL,
reference period, estimate type, confidence grade or granularity marker. The
only provenance-adjacent field is `source`, which takes the values `onet` or
`ph_native` and describes which branch of the generator ran, not where a number
came from.

---

## 4. Source claims versus source reality

Full detail in [`source-claims.csv`](source-claims.csv).

| Claimed in UI/README | Reproducible artifact in repo? | Verdict |
| --- | --- | --- |
| PSA LFS 2024 | `fetch_psa.py` targets a real PXWeb table, writes to gitignored `data/raw/`, **and no module reads it** | **Unsupported** — orphaned fetcher |
| PSA OWS 2024 | same fetcher, and the table is by *industry* not occupation | **Unsupported** |
| PSA Survey on Overseas Filipinos 2024 | no code, no file, no URL | **Unsupported** — hard-coded constants |
| O\*NET 30.2 | downloaded, parsed, used for education and descriptions | **Supported**, but unlabelled as US-derived |
| PhilJobNet | no code, no file, no URL | **Unsupported** — backs a constant |
| IBPAP | no code, no file, no URL | **Unsupported** |
| POEA | no code, no file, no URL; POEA was absorbed into the **Department of Migrant Workers** in 2022, so the attribution is also out of date | **Unsupported** |

Six of seven cited sources have no reproducible artifact. The citation line at
`site/index.html:1003-1004` lends all seven the same apparent authority.

---

## 5. Aggregate / component overlap and double counting

Ten hand-written broad Philippine categories share a single group employment
budget with granular O\*NET occupations describing the same workers. Nine of the
ten overlap detectably:

| Philippine record | Its employment | Overlapping O\*NET titles | Their employment |
| --- | --- | --- | --- |
| Kasambahay (domestic workers) | from seed | Maids and Housekeeping Cleaners; Janitors and Cleaners; First-Line Supervisors of Housekeeping | 1 146 022 |
| Tricycle / jeepney drivers | from seed | Bus Drivers (School); Bus Drivers (Transit); Ambulance Drivers | 1 459 788 |
| Fisherfolk | from seed | Fishing and Hunting Workers; First-Line Supervisors of Farming, Fishing and Forestry | 1 419 534 |

Because the aggregate and its components draw from the same fixed budget, the
per-occupation figures are neither independent nor additive, and the treemap —
whose tile **area is employment** — visually double-counts these workers.

---

## 6. Reproducibility

| Property | Status |
| --- | --- |
| Clean checkout rebuilds published data | **No** — three required intermediates are gitignored |
| Rebuild works offline | **No** — requires the O\*NET download |
| LLM scores reproducible | **No** — single run, no seed, no raw responses, model unrecorded |
| Source files hashed | **No** |
| Retrieval dates recorded | **No** |
| Release manifest | **Does not exist** |
| Stale-artifact detection | **None** — `check.py` compares titles only |

---

## 7. Language review

`site/index.html` describes the exposure score as **"risk"** throughout:
"task reshaping risk" (lines 998, 1019, 1226), "Risk Vector Explainer" (1079),
"Risk vector:" (1771), and CSS/DOM identifiers `risk-panel`, `riskGauge`,
`riskMeaning`, `openRiskExplainer`. The colour ramp runs green → amber →
**red `rgb(220,53,69)`** (`exposureColor`, line 1352), the standard danger
signal.

`AGENTS.md` instructs agents to think in "Risk Vectors" and prescribes
"Green-Yellow-Red for risk".

Nothing in the interface tells a reader that exposure is not automation,
displacement or job loss. The only caveat present (line 997) distinguishes
generative AI from *robotics* — a narrower point — and appears in header prose
rather than beside the score.

---

## 8. Classification of every published metric

| Metric | Actual class | Presented as |
| --- | --- | --- |
| `jobs` employment | **Placeholder / synthetic** — hard-coded group total split by title keywords | observed employment; drives tile area and every headline |
| `pay` wage | **Placeholder** — constant per category | "Avg. wage (PSA OWS 2024)" |
| `outlook` hiring intensity | **Placeholder** — literal `50` | "based on PhilJobNet postings" |
| `informal_share` | **Placeholder** — constant per category | "Estimated share" (the only near-honest label) |
| `ofw_share` | **Proxy, mislabelled** — P(occupation\|OFW) shown as P(OFW\|occupation) | "Share of PSOC group working overseas (PSA SOF 2024)" |
| `education` | **Proxy** — real O\*NET Job Zone, US construct | "Typical education level required for entry" |
| `exposure` | **Model-derived, unreplicated, anchored** | a 0–10 "risk" score |
| `exposure_rationale` | **Model-generated text** | displayed as explanation of fact |
| Total jobs (49M) | **Derived from placeholder** | headline |
| Monthly payroll | **Derived from two placeholders** | headline |
| Wages exposed | **Derived from three placeholders** | headline |
| OFW-linked jobs | **Derived from placeholder × mislabelled proxy** | headline |

**No published numeric field in v1 is a directly observed Philippine statistic.**
The single value with a real, citable source — O\*NET Job Zone — describes the
United States.

---

## 9. Audit verdict against the stated hypotheses

| Hypothesis | Verdict |
| --- | --- |
| Describes 173 occupations despite 500+ claims | **Partly** — 173 confirmed and hard-coded in two places; no 500+ claim exists in this repository |
| Starts from US O\*NET/SOC, not PSOC | **Confirmed** |
| Maps SOC to PSOC heuristically | **Confirmed** — bare dict, 22 majors, no match metadata, PSOC 9 unreachable, PSOC 0 absent |
| Manually defines PSOC group employment totals | **Confirmed** — `GROUP_TOTALS`, uncited |
| Distributes totals by title multipliers | **Confirmed** — and 86.7% of rows share a value with another row |
| Preserves curated seed employment | **Confirmed** |
| Category-level wage constants | **Confirmed** — 11 values for 173 occupations |
| Category-level informal constants | **Confirmed** — 10 values |
| PSOC-major OFW constants as occupation values | **Confirmed, and it is the wrong conditional** — constants sum to 1.02 |
| Hiring intensity = 50 for all | **Confirmed** — one distinct value, backs 7 UI statistics |
| Single-prompt LLM scores | **Confirmed** |
| Scores conditioned on weak/synthetic metrics | **Confirmed** — and the prompt anchors the output mean |
| Risk-oriented red/yellow/green presentation | **Confirmed** |
| Insufficient row-level provenance | **Confirmed** — zero provenance fields |
| Sources cited without traceable values | **Confirmed** — 6 of 7 sources unsupported |

---

## 10. Consequences for the rebuild

1. Every numeric field except O\*NET education must be **withdrawn**, not
   relabelled. Relabelling a value that was never measured still publishes it.
2. PSOC must become the canonical key, with major group 0 and major group 9
   properly represented.
3. Employment, wages, informality and OFW figures must come from PSA tables at
   the granularity PSA actually publishes, or be marked unavailable.
4. "OFW share" cannot be reconstructed from an OFW distribution; the metric name
   must change to what the source supports.
5. Exposure must be rebuilt task-first, replicated, with provenance and a
   reported stability measure, under a prompt that does not anchor its own
   distribution and that is not fed labour-market statistics as evidence.
6. Hiring intensity must be deleted outright. No source for it exists.
7. The treemap's area-equals-employment encoding must be withdrawn with the
   employment data that justified it.
