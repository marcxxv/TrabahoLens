# data/derived — v2

Derived artifacts now live in `data/canonical/` (the normalised PSOC tables)
and `data/release/` (the release manifest). This directory is kept for
intermediates produced by future acquisition steps.

The v1 files that used to live here — `occupations_ph.csv` and
`scores_ai_only.json` — were moved verbatim to `data/legacy/v1/`. They are
byte-identical copies, not rewrites. Nothing was deleted: they were removed
from here so a reader cannot mistake a withdrawn dataset for a current one.

See `docs/migration-notes.md`.
