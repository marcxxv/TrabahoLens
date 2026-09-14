# Data licensing and attribution

**The repository's MIT licence applies to the code in this repository. It does
not apply to any third-party data.** Nothing in `LICENSE` grants you rights over
PSA statistics, O\*NET data, or any other source described here. Each source
carries its own terms, recorded separately below.

This is a good-faith reading by the project, not legal advice, and it has not
been reviewed by counsel. Where the terms are uncertain, that is said plainly
rather than resolved by assumption. Confirm with the publisher before
redistributing.

---

## Repository code

| | |
| --- | --- |
| Licence | MIT (see `LICENSE`) |
| Covers | Python modules under `src/` and `scripts/`, the interface in `site/index.html`, the Makefile, CI configuration, and the documentation under `docs/` |
| Does not cover | Any data retrieved from a third party, whether or not it is committed |

---

## Philippine Statistics Authority (PSA)

Applies to: PSOC 2012, the Labor Force Survey, the Occupational Wages Survey,
the Survey on Overseas Filipinos, and informality statistics.

| | |
| --- | --- |
| Status in this release | **Not retrieved, not redistributed.** No PSA data is present in this repository. |
| Licence | PSA outputs are official Philippine government statistics. The PSA does not attach an open-data licence identifier (such as CC BY) to its statistical tables or classification volumes. Reuse is generally permitted with attribution; redistribution of whole datasets is not clearly granted. |
| Required attribution | Cite the PSA, the named survey or classification, and the round or edition. For example: *Philippine Statistics Authority, Labor Force Survey, October 2024.* |
| How this project handles it | Data is acquired by script into `data/raw/`, which is gitignored. Only the URL, retrieval timestamp and SHA-256 are committed, in `data/sources/retrieval-manifest.json`. Anyone can confirm they hold the same bytes without this repository redistributing them. |
| Open question | Whether bulk redistribution of PSA tables is permitted. Treated as **not permitted** until confirmed. |

**A caution that is about accuracy, not licensing.** Citing "PSA" is not the
same as citing a PSA figure. v1 credited PSA LFS, OWS and SOF in its interface
while publishing values that came from constants in its own source code. An
attribution line is a claim about provenance, and it should only appear where a
retrieval manifest entry backs it.

---

## O\*NET (U.S. Department of Labor)

| | |
| --- | --- |
| Status in this release | **Not retrieved, not redistributed.** |
| Licence | O\*NET data are provided by USDOL/ETA under the **Creative Commons Attribution 4.0 International (CC BY 4.0)** licence. Redistribution and adaptation are permitted with attribution. |
| Required attribution | *This product uses data from O\*NET OnLine by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA). O\*NET® is a trademark of USDOL/ETA. Used under CC BY 4.0.* |
| Trademark | O\*NET is a registered trademark of USDOL/ETA. The licence covers the data, not the mark; do not imply endorsement. |
| How this project handles it | Although CC BY 4.0 would permit vendoring the archive, it is downloaded by script and hashed rather than committed, so the repository stays small and the retrieved version stays verifiable. |

**Accuracy condition attached to use.** O\*NET describes **United States**
occupations. Any O\*NET-derived value displayed against a Philippine occupation
is a proxy and must carry that label and its crosswalk quality. This is a
methodological requirement, enforced by validation — not a licence term.

---

## PhilJobNet (DOLE)

| | |
| --- | --- |
| Status | **Not used.** No PhilJobNet data is present, and no PhilJobNet citation appears in the interface. |
| Licence | Not established. No terms were reviewed, because no data is used. |
| Before any use | Establish the access method and whether a public bulk download or API exists. Scraping is not appropriate where an official downloadable table or API exists — and where neither exists, the absence is itself a reason to reconsider. Document collection dates, deduplication of employer and posting duplicates, occupation coding, regional coverage, expiry handling and normalisation. |
| Naming requirement | Any resulting index is a **posting or platform demand signal**, never total hiring demand. Postings reflect employers who chose one government platform. |

v1 cited PhilJobNet to justify a field that was the literal constant `50`. The
field and the citation are both gone.

---

## IBPAP

| | |
| --- | --- |
| Status | **Not used.** |
| Licence | Not established. Industry association publications are typically all-rights-reserved; confirm before quoting figures. |
| Before any use | IBPAP publishes **industry-level** roadmaps and headcount projections. These are not occupational statistics. Assigning an industry projection to an occupation requires a documented mapping and an explicit caveat, and the result is not an official statistic. |

---

## POEA / Department of Migrant Workers (DMW)

| | |
| --- | --- |
| Status | **Not used.** The generic "POEA" attribution in v1's interface is removed. |
| Attribution note | POEA's functions were absorbed into the **Department of Migrant Workers** in 2022. Current deployment data is attributed to DMW; historical series keep their POEA attribution with the relevant date. |
| Licence | Not established. Philippine government administrative statistics, generally reusable with attribution; confirm for bulk redistribution. |
| Before any use | Identify the exact table. Deployment records are a **flow** of processed contracts, not a **stock** of workers, and are not comparable with LFS employment. |

---

## Model outputs (generative-AI task exposure)

| | |
| --- | --- |
| Status | **No scoring run has been executed.** `data/canonical/model_scores.csv` is header-only. |
| Ownership | Scores and raw responses are generated by this project. Provider terms govern the API calls that produce them; check your provider agreement before redistributing raw responses. |
| Storage | Raw responses are retained under `data/exposure/runs/<run_id>/` so any published score traces to the response that produced it. |
| Required statement | *This experimental score has not yet undergone independent labour-economist validation.* |
| Attribution | Cite the rubric version, prompt version, model provider, model id and scoring date. These are columns in `model_scores.csv`, not optional prose. |

---

## Design inspiration

The visualisation approach is inspired by
[karpathy.ai/jobs](https://karpathy.ai/jobs/). **No data is drawn from it**, and
no licence claim is made or needed. It is credited as inspiration in the
interface footer.

---

## If you reuse this project

1. The **code** is yours under MIT.
2. The **data** is not the project's to relicense. Obtain each source under its
   own terms and carry its attribution.
3. If you publish figures derived from these sources, carry the estimate type,
   the source, the reference period and the granularity with them. A number
   stripped of its qualifications is how v1's problems began.
4. Do not present the exposure score as automation, displacement or job-loss
   probability. That is a methodological requirement of the rubric, and
   restating it is a condition of reusing the rubric.
