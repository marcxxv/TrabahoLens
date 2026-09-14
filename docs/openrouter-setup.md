# Running the exposure scorer

Optional. The repository ships **no** exposure scores, and the site runs without
an API key.

Read [`exposure-protocol.md`](exposure-protocol.md) before running anything: it
sets the preconditions, the release gates and the reporting rules. This page is
only the mechanics.

## Setup

```bash
cp .env.example .env
# add OPENROUTER_API_KEY=...
```

`.env` is gitignored and a test fails the build if it is ever tracked.

## Running

```bash
make score-exposure MODEL=<provider/model-id> RUNS=5
make sensitivity
```

`MODEL` is required — a run without a recorded model id has no provenance, so
the Makefile refuses to guess one. Pass the provider-qualified id exactly as
your provider resolves it; it is recorded verbatim against every score.

`RUNS` defaults to 3 and must be at least 2. The harness refuses a single run:
one sample cannot report its own stability.

## What the harness will refuse

- **A prompt that states an expected distribution.** v1's prompt said
  `Expected average: ~3.5-4.5`, anchoring its own output before the model saw an
  occupation.
- **Labour-market inputs.** Employment, wages, OFW share and informality are not
  evidence of what a model can do with a task.
- **Fewer than two replicates.**
- **Missing task evidence.** The measure is task-based. If the task file is
  absent it raises rather than fall back to scoring job titles, which is what v1
  did.

These refusals are the point of the harness. Do not route around them.

## Output

Each invocation creates `data/exposure/runs/<run_id>/` containing `run.json` and
every raw response under `raw/`. **Reruns never overwrite history.**

`data/canonical/model_scores.csv` is rewritten from the latest run, with full
provenance per row — validation rejects a score missing any of the eleven
required fields.

## Model choice

Provider-qualified ids change over time; check your provider's current catalogue
if a slug stops resolving. Run at least two different models where you can:
between-model agreement is part of the validation battery, and a score only one
model has ever produced has no external check on it at all.

## A reminder

**This experimental score has not yet undergone independent labour-economist
validation.** Do not present it as automation, displacement or job-loss
probability, and do not convert it into a headcount or a peso figure.
