# Limitations

Current source review: 2026-09-28. This is a research preview, not a complete
occupation-level exposure product or an independently validated statistical service.

## Published evidence

`data/canonical/metric_observations.csv` contains 103 rows: 102 published
estimates and one missing SOF value. PSA employment is limited to PSOC major
groups; ILOSTAT adds sub-major employment, employee earnings and an education
share (see below). Not every layer is available: informal employment by
occupation and job-posting demand have no usable public source.
SOF is the distribution of the survey's OFWs across occupations, not the share
of a domestic occupation working overseas.

**ILO-processed layers.** Employment by sub-major group, employee earnings and
the advanced-education share come from the ILO's tabulation of the Philippine
Labor Force Survey. They differ from PSA's own published totals (the 2024
employed total is about 2.7% lower), cover employees only for earnings, and
describe who works in a group, not what its jobs require. Earnings are by major
group, so they cannot rank individual occupations. The ILO series publishes the
same median (PHP 30,416.67) for Managers and Professionals; it is kept as
published and not smoothed, and the interface says so.

`data/reference/ows_wage_benchmarks.csv` contains 693 source-native
occupation-by-industry records. 684 wage-rate estimates are available and nine
are withheld for inconsistent confidence intervals. Wage references are separate
from canonical PSOC and are not the unavailable basic-pay metric.

## Source discrepancies retained

- The pinned official 2022 PSOC workbook has 466 unique unit codes; the
  technical-notes webpage states 456. The parser retains the explicit workbook
  codes, records the mismatch and refuses a changed hash until reviewed.
- SOF's armed-forces percentage is blank even though precision fields are zero.
  It remains missing. The published percentages are not renormalised.
- OWS Table 1 rows 588–596 all carry the lower confidence bound 30,509.36,
  which belongs to row 587 (41,133.97 − 1.645 × 6,458.79). Their bounds do not
  consistently contain or centre on their own estimates. All nine are withheld,
  including the row whose estimate happens to fall inside the interval.
- OWS missing precision remains missing. CV above 10% is flagged and graded D.
  Passing these checks is not a guarantee that every publisher cell is correct.

## Scope and comparability

LFS is a household employment survey. No detailed occupation counts have been
derived from its major-group totals. A scan of all 2,502 PSA OpenSTAT tables on
2026-09-28 found no employment table finer than major occupation group. The
same matrix now carries a 2025 annual estimate, but PSA states it is computed
from preliminary monthly estimates that may change, so the final 2024 annual
estimate is retained. The sum of the selected source group cells
differs from the source total by one person after conversion from thousands;
this source rounding is retained.

SOF 2024 covers OFWs who departed October 2019–September 2024 and worked abroad
April–September 2024, with family still residing in the Philippines. It does not
cover every overseas Filipino. Standard errors are percentage points in the
source and are converted to share units alongside the values.

OWS August 2024 covers time-rated full-time workers in formal establishments
with 10 or more workers, including agriculture. Wage rate includes basic pay
plus regular/guaranteed cash allowances. It is not the income of all workers in
an occupation. Industry slices must never be averaged or summed into a national
occupational wage. The occupation-code version has not been confirmed, so no
PSOC-2022 join is asserted. Employment and OFW layers use explicit major-group
version correspondence; that does not authorise a detailed OWS correspondence.

## Exposure and other unavailable layers

Generative-AI task exposure is published as an experimental, full-coverage run
and is still not an independently validated measure. All 447 of the 447 PSOC
unit groups that carry PSA task statements are scored (894 dimension scores),
from 3,318 of the 3,362 task statements. The 44 excluded statements — 1.3% —
did not produce two parseable answers because the model sometimes renamed a
required field; they are excluded rather than repaired, and the 44 unit groups
they belong to carry a partial-coverage flag. Nineteen further unit groups have
no task statements in the workbook at all and carry no score.

Each occupation score is the median of a small, unweighted set of short PSOC
summary phrases — the source publishes no task-importance or time weights — so
it describes the model's judgement of those phrases, not measured work content
or adoption. O*NET task data exists but no accepted Philippine correspondence
exists, and the v1 scores are not a fallback. Education, hiring intensity and
occupation-level informality remain unavailable; no compatible verified
observations have been acquired.

The published layer is scored by one model, `deepseek-v4.1-flash` through
NYO, at temperature 0 with two successful attempts per task. Two consequences
are disclosed rather than adjusted for:

- **The scale is uncalibrated.** A 4 means the model judged the task statement
  to show high generative-AI task exposure; it does not mean a 4-in-5 chance of
  anything. On a 135-task shared sample, DeepSeek scored 0.70 points higher on
  average than `claude-sonnet-5` (higher on 94 tasks, lower on 1), and
  `glm-5.3-flash` scored 0.48 higher than Claude; the two cheap models agreed
  with each other within 0.21. The shift is reported, not rescaled — inventing
  a correction would be a fabricated calibration.
- **Attempt agreement is not stability.** At temperature 0 repeated attempts
  reproduce the same answer by construction, so the published agreement
  statistic measures provider reproducibility only. It is not evidence that the
  judgement would survive a changed prompt, model or occupation context.

**This experimental score has not yet undergone independent labour-economist
validation.** No Philippine labour statistician has reviewed the release.
Multi-model agreement is now measured and published, but human review,
Philippine-context validation and an accepted external benchmark must be
completed before these scores are presented as anything more than experimental.
See `docs/sensitivity-report.md` for the full run history and agreement figures.

## Validation boundaries

Automated checks establish source traceability, selected table structure,
numeric consistency, missing-value handling and reproducibility. They cannot
establish absence of all publisher errors, assess every sampling assumption, or
replace expert review. Hash pins prevent silent source changes, but an update
requires another source review. The language scanner and placeholder detector
are heuristic backstops, not proofs of statistical validity.

The dashboard uses observed employment to size the employment map; published
OFW shares to size its separate map; and equal record areas for wage references.
Small boxes can be inspected by zoom, keyboard or table view. Filtered shares
retain their original denominator. No missing value is filled to improve visual
density.

No production deployment, merge or Philippine AI Report integration is part of
this local validation pass.
