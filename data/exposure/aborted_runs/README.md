# Aborted scoring attempts

Scoring directories here are **not runs**. Each was interrupted before the
harness wrote its `run.json` manifest, so it has no recorded selection, rubric
version, prompt version or aggregate scores, and nothing in it may be published,
cited as a result or resumed as if it were a run.

They are retained rather than deleted because the attempt files contain paid
model responses and their exact request payloads, which may be needed if a
provider dispute or an audit asks what was actually sent.

| Directory | What happened |
| --- | --- |
| `20260928T154000Z__claude-sonnet-5__6fc50aba` | Session started 2026-09-28 15:40Z over 16 PSOC unit groups; 105 of 216 calls failed with provider `RuntimeError` before the process stopped. 111 succeeded. No manifest was written. |

To retry the same work, start a fresh scored run with `make score-exposure`; do
not copy from here. Complete runs live in `data/exposure/runs/` and are never
overwritten.
