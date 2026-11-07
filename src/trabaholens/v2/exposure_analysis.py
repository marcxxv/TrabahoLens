"""Stability and sensitivity analysis over exposure scoring runs.

Reads every run under ``data/exposure/runs/`` and reports:

* within-model stability (disagreement across repeated attempts in the same run);
* between-model agreement (when two or more runs used different models);
* task-weighting sensitivity (unweighted vs importance-weighted aggregation);
* crosswalk-quality sensitivity (does score depend on how good the mapping was);
* face-validity slices — highest and lowest scoring occupations, and the
  physical, high-touch and mixed occupations that a task-exposure measure is
  most likely to get wrong.

It reports honestly on an empty corpus: with no runs it says so and exits
without inventing an analysis.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from .paths import DOCS_DIR, EXPOSURE_RUNS_DIR, ensure_parent, rel

REPORT_PATH = DOCS_DIR / "sensitivity-report.md"

# Occupations whose scores must be inspected by hand before any release, chosen
# because they are where a task-based measure is most likely to mislead.
FACE_VALIDITY_WATCHLIST = {
    "physical_and_embodied": [
        "9 Elementary Occupations",
        "6 Skilled Agricultural, Forestry and Fishery Workers",
        "71 Building and Related Trades Workers",
        "83 Drivers and Mobile Plant Operators",
    ],
    "high_touch_service": [
        "53 Personal Care Workers",
        "54 Protective Services Workers",
        "51 Personal Service Workers",
        "32 Health Associate Professionals",
    ],
    "mixed_digital_and_embodied": [
        "22 Health Professionals",
        "23 Teaching Professionals",
        "31 Science and Engineering Associate Professionals",
        "74 Electrical and Electronic Trades Workers",
    ],
    "philippine_specific_concern": [
        "91 Cleaners and Helpers (kasambahay, domestic work)",
        "95 Street and Related Sales and Service Workers (vendors)",
        "83 Drivers and Mobile Plant Operators (tricycle, jeepney, delivery riders)",
        "62 Market-oriented Skilled Forestry, Fishery and Hunting Workers (fisherfolk)",
        "35 Information and Communications Technicians (BPO and contact-centre work)",
    ],
}


def load_runs() -> list[dict[str, Any]]:
    runs = []
    if not EXPOSURE_RUNS_DIR.exists():
        return runs
    for run_json in sorted(EXPOSURE_RUNS_DIR.glob("*/run.json")):
        runs.append(json.loads(run_json.read_text(encoding="utf-8")))
    return runs


def within_model_stability(run: dict[str, Any]) -> dict[str, Any]:
    ranges: list[int] = []
    stdevs: list[float] = []
    agreements: list[float] = []
    unstable: list[str] = []
    for entry in run.get("tasks", []):
        consensus = entry["consensus"]["technical_task_exposure"]
        if consensus.get("range") is None:
            continue
        values = consensus.get("values") or []
        ranges.append(consensus["range"])
        stdevs.append(statistics.pstdev(values) if len(values) > 1 else 0.0)
        if consensus.get("agreement") is not None:
            agreements.append(float(consensus["agreement"]))
        # The release gate: a task whose attempts span more than one point is
        # reported unstable. Consensus entries carry no "stability" field.
        if consensus["range"] > 1:
            unstable.append(entry["task_id"])
    if not ranges:
        return {"tasks_with_repeated_attempts": 0}
    result = {
        "tasks_with_repeated_attempts": len(ranges),
        "mean_attempt_range": round(statistics.mean(ranges), 4),
        "max_attempt_range": max(ranges),
        "mean_attempt_stdev": round(statistics.mean(stdevs), 4),
        "mean_attempt_agreement": (
            round(statistics.mean(agreements), 4) if agreements else None
        ),
        "unstable_task_count": len(unstable),
        "unstable_share": round(len(unstable) / len(ranges), 4),
        "unstable_definition": "attempt range greater than one point",
        "unstable_task_ids": unstable[:25],
    }
    if run.get("temperature") == 0.0:
        result["temperature_zero_note"] = (
            "Scored at temperature 0, so identical attempts are expected by "
            "construction. Zero disagreement here measures provider "
            "reproducibility only; it is not evidence that the judgement is "
            "stable under a different prompt, model or occupation context."
        )
    return result


def between_model_agreement(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Signed and absolute agreement between models, within one rubric version.

    Scores from different rubric or prompt versions are not on the same scale,
    so they are never compared: a 0.2.0 pilot and a 0.3.0 run of the same model
    are different instruments. Runs are grouped by (model, rubric, prompt) and
    only groups sharing both versions are paired.
    """
    by_key: dict[tuple[str, str, str], dict[str, float]] = defaultdict(dict)
    for run in runs:
        key = (
            run["model_id"],
            str(run.get("rubric_version", "")),
            str(run.get("prompt_version", "")),
        )
        for entry in run.get("tasks", []):
            score = entry["consensus"]["technical_task_exposure"].get("median")
            if score is not None:
                by_key[key][entry["task_id"]] = score

    if len({key[0] for key in by_key}) < 2:
        return {
            "models_compared": sorted({key[0] for key in by_key}),
            "status": "not_possible",
            "reason": "Between-model agreement needs runs from at least two distinct models.",
        }

    pairs = []
    keys = sorted(by_key)
    for i, left_key in enumerate(keys):
        for right_key in keys[i + 1 :]:
            if left_key == right_key:
                continue
            # Same instrument, different model. Anything else is not a comparison.
            if left_key[1:] != right_key[1:]:
                continue
            left, right = left_key[0], right_key[0]
            if left == right:
                continue
            shared = sorted(set(by_key[left_key]) & set(by_key[right_key]))
            if not shared:
                continue
            diffs = [abs(by_key[left_key][t] - by_key[right_key][t]) for t in shared]
            signed = [by_key[right_key][t] - by_key[left_key][t] for t in shared]
            exact = sum(1 for d in diffs if d == 0)
            pairs.append(
                {
                    "model_a": left,
                    "model_b": right,
                    "rubric_version": left_key[1],
                    "prompt_version": left_key[2],
                    "tasks_compared": len(shared),
                    "mean_absolute_difference": round(statistics.mean(diffs), 4),
                    "max_absolute_difference": max(diffs),
                    "exact_agreement_share": round(exact / len(shared), 4),
                    "within_one_point_share": round(sum(1 for d in diffs if d <= 1) / len(shared), 4),
                    # Signed so a systematic shift is not reported as mere noise:
                    # positive means model_b scored higher than model_a.
                    "mean_signed_difference": round(statistics.mean(signed), 4),
                    "model_b_higher_share": round(sum(1 for s in signed if s > 0) / len(shared), 4),
                    "model_b_lower_share": round(sum(1 for s in signed if s < 0) / len(shared), 4),
                }
            )
    if not pairs:
        return {
            "models_compared": sorted({key[0] for key in by_key}),
            "status": "not_possible",
            "reason": "No two models share a rubric and prompt version, so nothing is comparable.",
        }
    return {
        "models_compared": sorted({key[0] for key in by_key}),
        "status": "computed",
        "pairs": pairs,
    }


def weighting_sensitivity(run: dict[str, Any]) -> dict[str, Any]:
    from .exposure_runs import weighted_median

    by_occupation: dict[str, list[dict]] = defaultdict(list)
    for entry in run.get("tasks", []):
        by_occupation[entry["task"].get("psoc_code", "")].append(entry)

    diffs = []
    for psoc_code, entries in by_occupation.items():
        pairs = []
        for entry in entries:
            value = entry.get("consensus", {}).get("technical_task_exposure", {}).get("median")
            try:
                weight = float(entry.get("task", {}).get("task_importance") or 0)
            except (TypeError, ValueError):
                weight = 0
            if value is not None and weight > 0:
                pairs.append((value, weight))
        if not pairs:
            continue
        unweighted = statistics.median(value for value, _ in pairs)
        weighted = weighted_median(
            [value for value, _ in pairs], [weight for _, weight in pairs]
        )
        diffs.append({"psoc_code": psoc_code, "unweighted_median": unweighted,
                      "importance_weighted_median": weighted,
                      "category_shift": weighted - unweighted})

    if not diffs:
        return {"status": "not_possible",
                "reason": ("No task carries a positive importance weight. PSA's PSOC task "
                           "statements publish no importance scores, so an importance-weighted "
                           "aggregate cannot be computed from this task source.")}
    magnitudes = [abs(d["category_shift"]) for d in diffs]
    return {
        "status": "computed",
        "occupations": len(diffs),
        "median_absolute_category_shift": statistics.median(magnitudes),
        "max_absolute_difference": round(max(magnitudes), 4),
        "largest_shifts": sorted(diffs, key=lambda d: -abs(d["category_shift"]))[:10],
    }


def crosswalk_quality_sensitivity(run: dict[str, Any]) -> dict[str, Any]:
    by_quality: dict[str, list[float]] = defaultdict(list)
    for entry in run.get("tasks", []):
        score = entry["consensus"]["technical_task_exposure"].get("median")
        if score is None:
            continue
        by_quality[entry["task"].get("crosswalk_match_quality") or "unknown"].append(score)
    if not by_quality:
        return {"status": "not_possible", "reason": "No scored tasks carry a crosswalk quality."}
    if len(by_quality) == 1:
        only = next(iter(by_quality))
        return {
            "status": "computed",
            "by_quality": {
                only: {
                    "tasks": len(by_quality[only]),
                    "median_score": statistics.median(by_quality[only]),
                    "distribution": {
                        str(score): by_quality[only].count(score)
                        for score in sorted(set(by_quality[only]))
                    },
                }
            },
            "interpretation": (
                f"Every scored task comes from the single crosswalk band '{only}' "
                "(PSA task statements are native PSOC, so no crosswalk is involved). "
                "No comparison across bands is possible or needed."
            ),
        }
    return {
        "status": "computed",
        "by_quality": {
            quality: {
                "tasks": len(values),
                "median_score": statistics.median(values),
                "distribution": {str(score): values.count(score) for score in sorted(set(values))},
            }
            for quality, values in sorted(by_quality.items())
        },
        "interpretation": (
            "A systematic difference in median/category distribution across crosswalk quality bands "
            "means the measure is partly reporting mapping quality rather than task "
            "content, and the low-quality band should be suppressed."
        ),
    }


def face_validity_slices(run: dict[str, Any]) -> dict[str, Any]:
    """Highest and lowest scoring unit groups, for a human to sanity-check.

    This is not a verdict. It is the shortlist a reviewer reads first: a
    physical trade near the top or a documentation-heavy group at the bottom is
    a signal that the task list, not the work, was scored.
    """
    rollup = run.get("occupation_rollup") or {}
    titles: dict[str, str] = {}
    for entry in run.get("tasks", []):
        code = entry["task"].get("psoc_code", "")
        titles.setdefault(code, entry["task"].get("occupation_title", ""))

    rows = []
    for code, dimensions in rollup.items():
        dimension = dimensions.get("technical_task_exposure") or {}
        median = dimension.get("median")
        if median is None:
            continue
        rows.append(
            {
                "psoc_code": code,
                "title": titles.get(code, ""),
                "technical_task_exposure_median": median,
                "tasks": dimension.get("n_tasks"),
            }
        )
    if not rows:
        return {"status": "not_possible", "reason": "No occupation rollup in this run."}
    rows.sort(key=lambda row: (-row["technical_task_exposure_median"], row["psoc_code"]))
    return {
        "status": "computed",
        "occupations": len(rows),
        "highest": rows[:5],
        "lowest": sorted(rows[-5:], key=lambda row: (row["technical_task_exposure_median"], row["psoc_code"])),
        "note": ("Shortlist for manual review. A physical trade at the top or a "
                 "documentation-heavy group at the bottom means the task list may "
                 "have been scored instead of the work."),
    }


def render_report(runs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Exposure scoring — stability and sensitivity report")
    add("")
    add(f"Generated by `{rel(Path(__file__))}` · `make sensitivity`")
    add("")
    add("> This experimental score has not yet undergone independent")
    add("> labour-economist validation.")
    add("")

    if not runs:
        add("## Status: no scoring runs exist")
        add("")
        add("`data/exposure/runs/` is empty, so there is nothing to analyse. See")
        add("`docs/limitations.md`.")
        add("")
        add("No exposure score is published in this release. The v1 scores are **not**")
        add("carried forward: they were a single unreplicated run under a prompt that")
        add("stated a target average, conditioned on synthetic labour-market inputs,")
        add("with no model identifier recorded. They remain readable under")
        add("`data/legacy/v1/` as evidence about v1 and are not republished.")
        add("")
        add("## What this report will contain once a run exists")
        add("")
        add("| Analysis | Method | Release gate |")
        add("| --- | --- | --- |")
        add("| Within-model stability | Range and category agreement across repeated attempts with the same model and prompt | A task whose attempts span more than 1 point is reported unstable; an occupation where more than 25% of tasks are unstable is not published as a point score |")
        add("| Between-model agreement | Mean absolute difference and exact-agreement share across models | Reported; large disagreement is published rather than resolved by choosing a favourite |")
        add("| Prompt-wording sensitivity | Re-run under a variant prompt at the same rubric version | A dimension that moves materially on paraphrase is reported as prompt-sensitive |")
        add("| Task-weighting sensitivity | Unweighted vs importance-weighted aggregation | Both published; never averaged together |")
        add("| Crosswalk-quality sensitivity | Mean score by crosswalk match quality | A systematic gradient means low-quality mappings are suppressed |")
        add("| Comparison with an established methodology | Against a published task-exposure study where licensing permits | Reported as concordance, not as validation |")
        add("| Face validity | Manual review of the watchlist below | Reviewer sign-off recorded in `human_review_status` |")
        add("")
        add("## Face-validity watchlist")
        add("")
        add("These groups are where a task-based measure is most likely to mislead, so")
        add("they are reviewed by hand before any release rather than sampled at random.")
        add("")
        for group, items in FACE_VALIDITY_WATCHLIST.items():
            add(f"**{group.replace('_', ' ').capitalize()}**")
            add("")
            for item in items:
                add(f"- {item}")
            add("")
        add("Specific failure modes to look for:")
        add("")
        add("- **Physical and embodied work scored above 1 on dimension A.** Usually a sign")
        add("  the model scored the occupation's documentation rather than its work.")
        add("- **High-touch service scored high on A and low on B.** The two are")
        add("  independent; a care role that scores low on B has been misread.")
        add("- **Mixed occupations collapsing to their digital half.** A nurse's charting")
        add("  is not a nurse's job; check the task list is not documentation-heavy.")
        add("- **Philippine-specific work scored from a US task profile.** Kasambahay,")
        add("  tricycle and jeepney driving, street vending and fisherfolk have no close")
        add("  O\\*NET analogue; a confident score here is a crosswalk failure, and")
        add("  computed evidence confidence should be low.")
        add("- **BPO and contact-centre work.** The occupation most exposed to this")
        add("  measure's headline framing in the Philippines, and the one where the gap")
        add("  between task exposure and employment outcome is widest. Treat any")
        add("  reporting of it with particular care.")
        return "\n".join(lines) + "\n"

    add(f"Runs analysed: **{len(runs)}**")
    add("")
    latest = max(runs, key=lambda run: run.get("scoring_date", ""))
    latest_instrument = (latest.get("rubric_version"), latest.get("prompt_version"))
    add(f"Agreement is only computed between runs sharing a rubric and prompt version. "
        f"The current instrument is rubric `{latest_instrument[0]}`, prompt "
        f"`{latest_instrument[1]}`; runs at any other version are history.")
    add("")
    for run in runs:
        add(f"## Run `{run['run_id']}`")
        add("")
        add(f"- model: `{run['model_id']}` (provider `{run['model_provider']}`)")
        add(f"- rubric `{run['rubric_version']}`, prompt `{run['prompt_version']}`")
        if (run.get("rubric_version"), run.get("prompt_version")) != latest_instrument:
            add("- **superseded instrument** — a different rubric or prompt version; its "
                "scores are not comparable with the current layer")
        add(f"- temperature {run['temperature']}, repeated attempts {run.get('attempted_replicates', run.get('run_count'))}")
        if run.get("temperature_note"):
            add(f"- temperature note: {run['temperature_note']}")
        selection = run.get("selection") or {}
        scope = ("complete task file" if selection.get("complete_task_file")
                 else "pilot sample of the task file")
        add(f"- scored {run.get('task_count')} tasks on {run['scoring_date']} ({scope})")
        add(f"- human review status: `{run.get('human_review_status')}`")
        add("")
        add("### Within-model stability")
        add("")
        add("```json")
        add(json.dumps(within_model_stability(run), indent=2))
        add("```")
        add("")
        add("### Task-weighting sensitivity")
        add("")
        add("```json")
        add(json.dumps(weighting_sensitivity(run), indent=2))
        add("```")
        add("")
        add("### Crosswalk-quality sensitivity")
        add("")
        add("```json")
        add(json.dumps(crosswalk_quality_sensitivity(run), indent=2))
        add("```")
        add("")
        add("### Face validity — highest and lowest scoring groups")
        add("")
        add("```json")
        add(json.dumps(face_validity_slices(run), indent=2))
        add("```")
        add("")

    add("## Between-model agreement")
    add("")
    add("```json")
    add(json.dumps(between_model_agreement(runs), indent=2))
    add("```")
    add("")
    add("## Outstanding")
    add("")
    add("- Prompt-wording sensitivity requires a second prompt version at the same")
    add("  rubric version. Not yet run.")
    add("- Comparison with an established task-exposure methodology: not yet run.")
    add("- Independent labour-economist review: none.")
    return "\n".join(lines) + "\n"


def main() -> None:
    runs = load_runs()
    ensure_parent(REPORT_PATH)
    REPORT_PATH.write_text(render_report(runs), encoding="utf-8")
    print(f"Wrote {rel(REPORT_PATH)} ({len(runs)} run(s) analysed)")


if __name__ == "__main__":
    main()
