# Limitations

**The short version.** This release publishes no numbers. It publishes the
structure, the rules and the honest account of what is missing. Everything below
explains why, and what would change it.

---

## 1. No metric value is published

Not one. `data/canonical/metric_observations.csv` contains 30 rows and all 30
have an empty `metric_value`.

Every source the project needs was unreachable from the build environment. The
attempts are recorded, with timestamps, in
`data/sources/retrieval-manifest.json`:

| Host | Source | Result |
| --- | --- | --- |
| `psa.gov.ph` | PSOC 2012 volume, SOF | HTTP 403 at the egress proxy |
| `openstat.psa.gov.ph` | LFS, OWS | HTTP 403 at the egress proxy |
| `www.onetcenter.org` | O\*NET 30.2 | HTTP 403 at the egress proxy |
| `openrouter.ai` | Exposure scoring | HTTP 403 at the egress proxy |

`OPENROUTER_API_KEY` is also unset.

**What would change it.** Run `make fetch-data` from a network that permits
these hosts. The acquisition code, the hashing, the manifest and the validators
are complete and tested; only the bytes are missing.

**Why nothing was substituted.** The alternative was to keep v1's numbers while
improving the machinery around them. That would have produced a more impressive
dashboard making the same false claims, which is the failure mode this rebuild
exists to correct.

---

## 2. The PSOC code list is unverified

The PSOC 2012 major and sub-major groups in `classifications.csv` were entered
from ISCO-08-aligned classification documentation, **not** from the PSA volume,
which could not be retrieved.

PSOC 2012 is built on ISCO-08, so the major and sub-major skeleton should
correspond — but the PSA adds Philippine-specific groups and renames others, and
those departures are exactly what an ISCO-derived list cannot capture. This is
why the list stops at sub-major level: minor and unit groups are where the
divergence would be largest.

Every row carries `verification_status = unverified_pending_source`, and a
validator fails the build if any row loses that marker.

**What would change it.** Retrieve the PSA PSOC 2012 volume, diff it line by
line, correct any divergence, and set `verified_against_source`.

---

## 3. There are no detailed occupations

The canonical table holds 10 major groups and 43 sub-major groups. Nothing
finer.

This is a real loss of resolution against v1, which showed 173 named
occupations. That resolution was not real: those 173 were US O\*NET titles
selected by keyword ranking, 39 of which shared one identical employment
figure.

The consequence is that three metrics — occupation-level wages, O\*NET Job Zone,
and task exposure — have **no canonical unit to attach to**. They are recorded
in the release manifest as *not representable at current granularity*, which is
a different problem from *source not retrieved*, and is reported separately.

**What would change it.** The PSOC volume's minor and unit group lists.

---

## 4. No exposure score exists

The harness is built, guarded and tested against a stub client. It has never
run against a real model, because:

1. The provider is unreachable and no API key is set.
2. It requires **task statements**, and O\*NET could not be retrieved. Scoring
   titles instead is precisely the v1 defect; the harness raises rather than
   degrade to it.

The v1 scores are not a fallback and are not carried forward.

**This experimental score has not yet undergone independent labour-economist
validation.** No external expert, named or documented, has reviewed the rubric,
the prompt or any output.

---

## 5. Limitations that will persist after the data arrives

These do not go away when the network does.

### 5.1 OWS wages are not what most people assume

The Occupational Wages Survey covers non-agricultural establishments at or above
an employment threshold. It excludes agriculture, small establishments,
informal-sector workers, own-account and self-employed workers, and unpaid
family workers.

In the Philippines those exclusions cover a large share of employment. An OWS
wage is the wage of a covered establishment worker, and describing it as "the
average Filipino wage in this occupation" would be wrong even with the data in
hand.

### 5.2 OFW figures answer a different question

SOF supports **P(occupation | OFW)** — how OFWs are distributed across
occupation groups. It does not support **P(OFW | occupation)** — the share of an
occupation's workers who are overseas — without a domestic denominator on a
compatible universe.

Even with SOF retrieved, the within-occupation share stays unavailable until
that denominator exists. This tool will publish the distribution only.

A further structural limit: a household-based survey under-covers overseas
Filipinos with no household member remaining in the Philippines.

### 5.3 O\*NET describes the United States

Job Zones, task statements and importance ratings describe US occupations under
US conditions. Carried into a Philippine context they are proxies whose quality
is bounded by the crosswalk, and the crosswalk is weakest exactly where it
matters most: kasambahay, tricycle and jeepney driving, street vending,
fisherfolk and barangay health work have no close O\*NET analogue. A confident
score for those is a crosswalk failure, not a finding.

### 5.4 Adoption friction is judgement, not measurement

Dimension C of the exposure rubric asks how much regulation, liability,
connectivity, device access, employer scale and informality would slow
deployment. There is no dataset behind it. It is published as the most
speculative of the four dimensions, and it is never folded into the technical
exposure score.

### 5.5 The exposure measure cannot answer the question people ask

The question people bring to a tool like this is "will this job survive?" The
measure cannot answer it, and no amount of additional data would make it able
to. Task capability is one input to an employment outcome among many — adoption,
cost, regulation, demand, productivity, reorganisation, adaptation,
institutional capacity, and new work that does not exist yet.

Publishing a task-exposure number next to an occupation invites the inference
anyway. The interface resists it with a fixed disclaimer, non-hazard colouring,
four separate dimensions instead of one index, and a validator that rejects
job-loss vocabulary. That reduces the risk; it does not eliminate it.

### 5.6 A survey design that is not yet honoured

If LFS public-use microdata becomes available, estimates must be weighted,
standard errors or confidence intervals computed where variance guidance
permits, and low-sample cells suppressed or aggregated. None of that is
implemented, because no microdata is in hand. The schema has the fields
(`uncertainty_lower`, `uncertainty_upper`, `suppression_status`); the estimation
code does not exist.

### 5.7 Reference-period and seasonality effects

LFS rounds are quarterly and seasonal. SOF is an October rider. OWS is
biennial. Comparing across them, or reading any single round as "the" labour
market, will mislead. Every observation carries `reference_period` so this stays
visible, but the tool does not currently prevent a user from comparing
incomparable rounds.

---

## 6. What has not been reviewed

- **No Philippine labour statistician** has reviewed the schema, the metric
  definitions, or the PSOC structure.
- **No independent labour economist** has reviewed the exposure rubric.
- **No PSA correspondence** has confirmed which LFS, OWS, SOF and informality
  tables are publicly available at which occupational granularity. The registry
  records this as unverified rather than assuming an answer.
- **No licensing counsel** has reviewed the redistribution terms recorded in
  `data-licenses.md`. Those entries are a good-faith reading, flagged where
  uncertain.

---

## 7. Known weaknesses in the rebuild itself

Stated so a reviewer does not have to find them.

1. **The language validator is heuristic.** It bans hazard vocabulary and
   allows negated uses via a sentence-scoped negation window. That is a
   heuristic: a sufficiently convoluted sentence could evade it, and an unusual
   phrasing could trip it. Both directions are tested, but the check is a
   backstop for review, not a substitute.

2. **The double-counting check compares code prefixes.** It catches a parent
   published with its own descendants within PSOC. It would not catch
   double-counting between two classifications, which is how v1 actually did it
   — broad Philippine categories beside US O\*NET occupations. That case is
   currently prevented by there being only one classification in the canonical
   table, not by the validator.

3. **The placeholder-fill check uses a threshold.** Fewer than 10% distinct
   values across 5 or more published rows is flagged. A constant applied to
   four rows would pass. The threshold is a detector for the v1 pattern, not a
   proof of variety.

4. **Determinism is checked at a frozen timestamp.** `make determinism` pins
   `--frozen-time`. Real builds stamp the actual time, so two production builds
   differ in that field by design. Everything else is byte-stable.

5. **The audit's 500+ occupation claim is unresolved.** The brief listed a
   discrepancy between a 173-occupation dataset and a 500+ claim. No 500+ claim
   exists anywhere in this repository or its history. If one exists, it is on an
   external surface this branch cannot see or correct.

6. **`docs/audit/metric-inventory.csv` cites v1 line numbers** that were correct
   at commit `128dd22`. The v1 modules have since been retired to inert stubs,
   so some line numbers have shifted. The original files are preserved verbatim
   at that commit and in `data/legacy/v1/index_v1.html` for the interface.
