# data/reference — v2

The v1 curated seed file, `occupations_seed.json`, was moved verbatim to
`data/legacy/v1/occupations_seed.json`.

It is not a reference dataset in v2. The baseline audit found that its
`employment_estimate`, wage, informality and OFW values were manually written
without a source, and that only 8 of its 44 occupations survived into the
published v1 dataset anyway. The canonical reference in v2 is the PSOC
classification in `data/canonical/classifications.csv`.

See `docs/migration-notes.md`.
