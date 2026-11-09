# Hover preview and occupation profile redesign

Implementation notes, 2026-11-09. The release remains a research preview awaiting independent review.

The map's hover preview now presents the selected value, concise supporting
facts, and the evidence status. It keeps its measured bounds inside the viewport,
reuses its content while moving within a box, and moves using a CSS transform.

Clicking opens a responsive occupation profile: fixed title and close control,
selected measure, task coverage and physical-presence score where supplied,
published task-category distribution, expandable individual PSA task evidence,
and a readable source summary. The complete provenance remains available in an
expandable source record. On phones this is a bottom sheet with its own scrolling
body. The preview closes when the profile opens.

After local review, the preview was reduced to a 266px desktop card. The large
pointer-triggered canvas focus outline was removed; keyboard navigation keeps a
restrained focus cue. The profile now separates Overview, Task evidence and
Source, with an explicit Close control. Its score scale supports hover, keyboard
focus and tap to explain each category without changing the selected score.
The main colour legend offers the same category explanations.

Four main summary figures remain visible. Supporting task, coverage, model and
review figures live under Evidence & review, and every summary label has a
plain-language explanation available by hover, focus or tap. Method & limitations
now groups map encodings, an interactive rubric guide, the core limitations, and
expandable source notes. Scale descriptions paraphrase the existing v0.3.0
rubric; they do not change the scoring protocol.

All visuals use existing release fields. No metric values, scoring runs,
classifications, map weights, or unavailable states were changed. Source-native
wage codes are labelled as source codes, never PSOC codes. Unscored profiles
explicitly describe why no score is published.

Verification: the Python suite (227 tests), Node adapter and chart suite (7 tests), and
release validation pass. All 157 extended browser checks pass, plus 32 focused final text-fit checks. The browser QA covers source-value fidelity,
distribution counts, expandable tasks and provenance, missing and withheld
records, keyboard focus, hover placement, scrolling, reduced motion, and
320/390/820/1440px layouts. Browser QA uses headless Chrome; physical-device
acceptance remains a separate human check.

Run the interaction checks against a local server with `make browser-qa`.
`LOCAL_URL`, `LIVE_URL`, and `QA_OUT` can select the target pages and output folder;
set both URLs to the local preview for a fully local regression run. That does
not establish parity with the deployed site.


## Layer consistency, readability and charts — local follow-up

The sidebar uses 14px reading text, larger metadata and a 44px icon close
control. Search uses a subtle single-border focus treatment. Layer controls
keep identical dimensions across modes, and the desktop map starts at the same
position when switching layers. Desktop summaries and charts share a compact
strip; mobile layer controls and chart panels scroll horizontally within their
own regions rather than causing page overflow.

The overview includes a distribution, a breakdown and coverage. Exposure counts
PSOC unit groups equally, preserves half-point medians, shows explicitly bounded
tiers, and uses the existing included/listed PSA task counts for coverage.
Survey-layer distributions count source groups; wage distributions count
job-position-by-industry references. Ranked bars keep original source values
and their population labels. Empty views show an explanation rather than a plot.
No employment-weighted exposure or exposure-by-pay/education joins were added.

Chart arrangement takes inspiration from [Karpathy’s visualizer](https://karpathy.ai/jobs/)
and its [source](https://github.com/karpathy/jobs/blob/master/site/index.html).
The charts here use only TrabahoLens release data and retain its source scope.

Rendering reuses number formatters, coalesces pointer hover work per animation
frame, and skips canvas relayout when only header height changes. A single local
headless-Chrome comparison at 1440×900, with 463 rendered rectangles and 40 timed
draws after warmup, measured approximately 1.4ms median before and 0.6ms after;
slow samples stayed around 2ms. This measures the canvas draw function, not
end-to-end frame rate or physical-phone performance. No chart framework or new
runtime dependency was introduced.
