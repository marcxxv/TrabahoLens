# Changelog

## [2.0.0-pre] — credibility rebuild (branch `audit/rebuild-v2`)

A ground-up rebuild after an audit found that none of v1's published numeric
fields was an observed Philippine statistic. PSOC replaces O\*NET-SOC as the
canonical key; every value now carries its provenance; unsupported metrics were
withdrawn rather than relabelled.

**This release publishes no metric values** — no source could be retrieved from
the build environment, and v1's numbers were not carried forward to fill the
space.

Full detail: [`docs/changelog-v2.md`](docs/changelog-v2.md).
Evidence: [`docs/audit/baseline-audit.md`](docs/audit/baseline-audit.md).
Integration assessment: [`docs/readiness-report.md`](docs/readiness-report.md).

---

## Entries below describe v1 and are retained for the historical record

The features they announce were withdrawn by the rebuild above. The audit
explains what each one actually contained.

## [1.2.0] - 2026-05-03
### Added
- **PWA Integration**: Full manifest and theme support for home-screen installation.
- **Enhanced SEO**: Metadata for social sharing (OpenGraph, Twitter cards) and search indexing.
- **Bento UI Overhaul**: Modernized dashboard layout with "morphic" aesthetics and glassmorphic details.
- **Detailed Risk Panel**: An interactive drawer that explains AI risk vectors and economic footprints per occupation. *(Withdrawn in 2.0.0-pre: the economic footprints multiplied synthetic employment by category wage constants.)*
- **DataReceipt & ChartFrame**: New internal architectural patterns for data presentation.

### Changed
- **Documentation Sync**: Comprehensive audit and refinement of `README.md`, `CLAUDE.md`, `AGENTS.md`, and `CHANGELOG.md`.
- **UI Responsiveness**: Improved mobile layout for the treemap and stats grid.

## [1.1.0] - 2026-04-27
### Added
- **AI Exposure Refinement**: Narrowed focus to Generative AI and LLM-driven task displacement, removing conflation with machinery automation. *(The narrowing was real; the scoring remained a single unreplicated run under a prompt stating its own expected average.)*
- **New Scorer**: Implementation of `score_ai_only.py` using OpenRouter (Claude-3.5-Haiku). *(Retired in 2.0.0-pre; the model that produced the shipped scores was never recorded in the output.)*
- **Philippine-Specific Occupations**: Added coverage for "Kasambahay", "Tricycle Drivers", and "OFW Caregivers". *(These ten records shared an employment budget with O\*NET occupations describing the same workers.)*
- **i18n Infrastructure**: Initial support for English/Tagalog routing and translations.

## [1.0.0] - 2026-04-04
### Initial Release
- **Core Visualizer**: Treemap implementation based on Karpathy's jobs site. *(Withdrawn in 2.0.0-pre: tile area encoded employment, and that employment was synthetic.)*
- **Data Integration**: Integration of PSA (Philippine Statistics Authority) and O\*NET datasets. *(Only the O\*NET integration was real.)*
- **Static Pipeline**: Automated builds from CSV/JSON sources to `site/data.json`.
- **Theme System**: Minimalist dark-mode theme with interactive tooltips.
