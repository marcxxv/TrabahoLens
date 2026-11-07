# Validation record — 2026-09-28

## Passed

- `make check`: compilation and release validation.
- `make test`: 200 tests, including tests against original PSA workbooks and
  four JavaScript adapter/layout cases invoked by the suite.
- `make determinism`: two byte-identical release builds.
- `make check-stale`: generated artifacts match their inputs.
- `git diff --check` and JavaScript syntax check.
- Source replay: canonical tables reconstructed from verified raw inputs;
  OWS reference rows compared against a fresh extraction of the pinned workbook.
- Deployed stylesheet preserved verbatim, checked by SHA-256. Original shell
  hooks, unique IDs and JavaScript element targets checked automatically.
- Adapter tests reject incomplete provenance and fabricated withheld values;
  preserve the source populations and missing OFW cell; verify area weights.

The workbook reader reports a malformed publisher print-area name (`#N/A`) in
SOF. It does not change the selected cell values; extraction tests pass.

## Browser QA (Claude Code pass, same day)

The interaction layer was rewritten against the deployed page's own script,
downloaded from the deployment for comparison: compact-layout rule, tooltip
placement, label thresholds, group gaps, animated zoom, double-click and
double-tap zoom-to-box, pan and pinch. The data adapter was not changed.

`make browser-qa` (`scripts/browser_qa.mjs`) drives headless Google Chrome with
a fresh profile against `http://127.0.0.1:8000/` and the deployment, sending
real mouse, touch and keyboard input through the DevTools protocol. 61 of 61
checks passed:

- Canvas size equals the deployment at 1440×900, 820×1180 (touch) and 390×844
  (touch): 1400×1050, 820×968 and 390×480. No horizontal page overflow.
- Header height: desktop 542 px locally vs 559 px deployed; tablet 803 vs 866;
  mobile 1264 vs 1246.
- Hover tooltip, highlighted box, click-to-open drawer, close-button focus,
  Tab trap, Escape and overlay close, focus return and selection clearing.
- Double-click and double-tap zoom to a box without opening the drawer;
  Ctrl/⌘+wheel zoom; plain wheel scrolls the page; mouse and one-finger pan
  when zoomed; two-finger pinch; Escape resets zoom. A tap after these
  gestures still opens details.
- Arrow keys, Home/End, Enter/Space and +/- on the focused canvas.
- All seven layers: Employment 10 boxes; Wage references 684 boxes, 9
  withheld; OFW 9 boxes with the blank armed-forces cell missing. The four
  unavailable layers are selectable, draw no boxes and state their reason.
- Industry filter, search, table pagination, layer persistence on reload.
- CSV: 693 rows for the unfiltered wage layer; the nine withheld rows keep an
  empty value; every published value is numeric; provenance columns exist.
- A 503 on `data.json` shows an explicit error, hides the canvas and summary
  blocks and disables controls. No console errors occurred.

Screenshots of both sites at each size were compared by eye. The header,
layer strip, filter, legend, eight summary blocks in one row, bento grouping,
tooltip and drawer follow the deployed layout. Deliberate differences:
source-scoped copy, a seventh layer (Employment), search/table/export tools,
a neutral colour ramp instead of the deployed hazard-style ramps, and ten
employment boxes instead of 173 allocated occupations.

Headless Chrome is not a person on real devices, and matching geometry is not
user acceptance. `make check-stale` failed once without a diff after a
registry edit and passed on three later runs; the cause was not identified.

## Release boundary

19 published canonical major-group estimates; 684 available source-native wage
references, nine inconsistent wage records withheld. No model score, detailed
employment allocation, national occupation-wide wage, or unsupported layer has
been added. This record is not production approval or independent expert review.
No commit, push, merge or deployment was performed in either pass.
