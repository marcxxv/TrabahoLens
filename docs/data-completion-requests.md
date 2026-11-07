# Completing the original dashboard with defensible data

Checked 2026-09-28. This is a requirements list, not evidence that these data
have been obtained or that any request has been sent.

## What is usable now

- PSA 2024 annual LFS employment estimates at major-occupation-group level.
- PSA 2024 SOF occupation distribution, separately scoped to overseas workers.
- PSA August 2024 OWS occupation-by-industry wage references, including source
  precision where supplied. Inconsistent rows are quarantined.

These are historical survey estimates. “Accurate” here means faithfully
extracted, correctly scoped and traceable—not exact population measurements,
current live counts, or independently certified statistics.

## PSA request: detailed employment for the original box sizes

Ask PSA for a published table or custom tabulation of annual employed persons
by detailed occupation, preferably four-digit PSOC, for 2024 and the latest
comparable annual release. Request:

1. PSOC codes, titles, exact classification version, and correspondence for any
   revisions. Do not accept title-only matching.
2. National weighted employment estimates, units, universe, reference period,
   and annual estimation method—not sums of monthly estimates.
3. Standard errors, coefficients of variation, confidence intervals, sample
   counts where releasable, suppression rules and reliability guidance.
4. A stable publisher URL or an authorized source file, publication/revision
   date, explanatory notes and reuse terms.
5. An explanation if detail cannot be released reliably. Coarser data should
   remain coarse; an unavailable detailed estimate must remain unavailable.

If PSA offers microdata instead, obtain access under its terms and include
weights, sampling design documentation and a disclosure-safe tabulation plan.
Do not send personal records into an LLM. A survey statistician must review the
estimation method; public download access alone is not statistical validation.

**User action:** provide an existing official table/access arrangement if you
have one, or send this request to PSA. No request or purchase has been made on
your behalf. A dense employment-sized map cannot be promised until the
publisher supplies reliable detail.

## PSA clarification: wages and classification

Ask PSA to confirm the occupation-code version in the 2024 OWS workbook and
provide its correspondence to the 2022-updated PSOC. Table 1 heads the column
"PSIC/PSOC" without a version; the industry tables state 2009 PSIC. Ask whether
a corrected Table 1 exists for rows 588–596 (J58 Publishing), which all repeat
row 587's lower 90% bound of 30,509.36. The workbook publishes basic pay only
by industry and region (Tables 5–8), not by occupation, so an occupation-level
basic-pay metric cannot come from this release. Also ask why the PSOC workbook contains
466 unit groups while the classification webpage describes 456.

An OWS monthly wage rate includes regular cash allowances and covers the
survey's formal establishments. It is not automatically basic pay, nationwide
occupation-wide pay, or comparable to all LFS workers. Even a confirmed code
match does not remove these population and concept differences.

## AI task exposure: human review before model calls

The O*NET source is available, but a reviewed Philippine task correspondence
is not. An occupational/classification specialist needs to review code-based
correspondences and task applicability, not English-title resemblance. Then
run the versioned rubric with at least two successful repeated attempts,
retain disagreements, and review calibration and limitations independently.

Model credentials and a spending limit become relevant at that stage. Do not
purchase calls or publish scores simply to colour otherwise empty tiles.

## Other original controls

- Education needs occupation-level attainment data with a defined population.
- Posting demand needs permitted, dated job-posting records, deduplication,
  source coverage and a defined window. It must be labelled platform/posting
  demand, not nationwide hiring or an employment forecast. PSA OpenSTAT has
  ISLE Occupational Shortages and Surpluses tables (for example 1B3ES031,
  vacancies and applicants by major occupation group, establishments with 20+
  workers, July 2017–August 2022). These are establishment vacancies, not
  postings, and are older than the other layers. Using them would need a new,
  separately named metric; that is a product decision, not a substitute.
- Informality needs compatible occupation-level estimates and the publisher's
  definition; it cannot be inferred from occupation labels.

No paid API subscription is currently recommended. Assess coverage, licence,
classification, freshness and precision before asking the user to buy access.

## Philippine AI Report: public documentation, currently unavailable API

Documentation: https://philippineaireport.com/llms.txt and
https://philippineaireport.com/survey.md . Metadata:
https://philippineaireport.com/api/report-meta.json .

The documentation describes a self-administered survey of 179 practitioners
and leaders, with 41 questions, fielded June–December 2025. Question percentages
use respondents answering that question, not necessarily all respondents.
Small cells are suppressed or combined. These are practitioner responses,
not a probability-based national occupation employment or task-exposure table.
The metadata publication date also needs reconciliation with the field dates
before using it as a dated evidence series.

The documented no-auth REST endpoint is
https://swtwqrwsyedfamedawbm.supabase.co/functions/v1/survey-api/meta .
Direct reads on 2026-09-28, repeated later that day, returned HTTP 402 with
`exceed_db_size_quota`.
The response states the project owner must restore service. This is not proof
that an API credential or payment from the TrabahoLens user is required.

The documented MCP endpoint is
https://swtwqrwsyedfamedawbm.supabase.co/functions/v1/mcp . It is not installed
as a tool in this session; its functioning has not been verified. No survey
values were imported and no changes were made to Philippine AI Report.

**Optional manual route:** ask its owner to restore the public service or
provide a licensed aggregate export with denominators, questionnaire and
methodology. It could support a separately labelled adoption/context panel,
not replace PSA employment counts or populate occupation exposure scores.

## Visual acceptance

The deployed CSS, structure and interaction model are restored, and
`make browser-qa` passes 61 headless-Chrome checks at desktop, tablet and phone
sizes (see `docs/validation-2026-09-28.md`). What remains is a person using the
site on real devices and accepting it. This is not production approval.
