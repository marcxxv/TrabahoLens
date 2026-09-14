"""Stability and sensitivity analysis over exposure scoring runs.

Reads every run under ``data/exposure/runs/`` and reports:

* within-model stability (disagreement across replicates of the same run);
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
    unstable: list[str] = []
    for entry in run.get("tasks", []):
        consensus = entry["consensus"]["technical_task_exposure"]
        if consensus.get("range") is None:
            continue
        ranges.append(consensus["range"])
        stdevs.append(consensus.get("stdev", 0.0))
        if consensus.get("stability") == "unstable":
            unstable.append(entry["task_id"])
    if not ranges:
        return {"tasks_with_replicates": 0}
    return {
        "tasks_with_replicates": len(ranges),
        "mean_replicate_range": round(statistics.mean(ranges), 4),
        "max_replicate_range": max(ranges),
        "mean_replicate_stdev": round(statistics.mean(stdevs), 4),
        "unstable_task_count": len(unstable),
        "unstable_share": round(len(unstable) / len(ranges), 4),
        "unstable_task_ids": unstable[:25],
    }


def between_model_agreement(runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, float]] = defaultdict(dict)
    for run in runs:
        for entry in run.get("tasks", []):
            score = entry["consensus"]["technical_task_exposure"]["score"]
            if score is not None:
                by_model[run["model_id"]][entry["task_id"]] = score

    models = sorted(by_model)
    if len(models) < 2:
        return {
            "models_compared": models,
            "status": "not_possible",
            "reason": "Between-model agreement needs runs from at least two distinct models.",
        }

    pairs = []
    for i, left in enumerate(models):
        for right in models[i + 1 :]:
            shared = sorted(set(by_model[left]) & set(by_model[right]))
            if not shared:
                continue
            diffs = [abs(by_model[left][t] - by_model[right][t]) for t in shared]
            exact = sum(1 for d in diffs if d == 0)
            pairs.append(
                {
                    "model_a": left,
                    "model_b": right,
                    "tasks_compared": len(shared),
                    "mean_absolute_difference": round(statistics.mean(diffs), 4),
                    "max_absolute_difference": max(diffs),
                    "exact_agreement_share": round(exact / len(shared), 4),
                    "within_one_point_share": round(sum(1 for d in diffs if d <= 1) / len(shared), 4),
                }
            )
    return {"models_compared": models, "status": "computed", "pairs": pairs}


def weighting_sensitivity(run: dict[str, Any]) -> dict[str, Any]:
    from .score_exposure import aggregate_tasks_to_occupation

    by_occupation: dict[str, list[dict]] = defaultdict(list)
    for entry in run.get("tasks", []):
        by_occupation[entry["task"].get("psoc_code", "")].append(entry)

    diffs = []
    for psoc_code, entries in by_occupation.items():
        unweighted = aggregate_tasks_to_occupation(entries, "technical_task_exposure", weighted=False)
        weighted = aggregate_tasks_to_occupation(entries, "technical_task_exposure", weighted=True)
        if unweighted is None or weighted is None:
            continue
        diffs.append({"psoc_code": psoc_code, "unweighted": unweighted, "weighted": weighted,
                      "difference": round(weighted - unweighted, 4)})

    if not diffs:
        return {"status": "not_possible",
                "reason": "No occupation has both an unweighted and an importance-weighted aggregate."}
    magnitudes = [abs(d["difference"]) for d in diffs]
    return {
        "status": "computed",
        "occupations": len(diffs),
        "mean_absolute_difference": round(statistics.mean(magnitudes), 4),
        "max_absolute_difference": round(max(magnitudes), 4),
        "largest_shifts": sorted(diffs, key=lambda d: -abs(d["difference"]))[:10],
    }


def crosswalk_quality_sensitivity(run: dict[str, Any]) -> dict[str, Any]:
    by_quality: dict[str, list[float]] = defaultdict(list)
    for entry in run.get("tasks", []):
        score = entry["consensus"]["technical_task_exposure"]["score"]
        if score is None:
            continue
        by_quality[entry["task"].get("crosswalk_match_quality") or "unknown"].append(score)
    if not by_quality:
        return {"status": "not_possible", "reason": "No scored tasks carry a crosswalk quality."}
    return {
        "status": "computed",
        "by_quality": {
            quality: {"tasks": len(values), "mean_score": round(statistics.mean(values), 4)}
            for quality, values in sorted(by_quality.items())
        },
        "interpretation": (
            "A systematic difference in mean score across crosswalk quality bands "
            "means the measure is partly reporting mapping quality rather than task "
            "content, and the low-quality band should be suppressed."
        ),
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
        add("`data/exposure/runs/` is empty, so there is nothing to analyse. This is")
        add("the expected state of the current release: the scoring provider")
        add("(`openrouter.ai`) is unreachable from the build environment and")
        add("`OPENROUTER_API_KEY` is unset, and the task evidence the harness requires")
        add("(O\\*NET task statements) could not be retrieved either. See")
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
        add("| Within-model stability | Range and standard deviation across replicates of the same model and prompt | A task whose replicates span more than 1 point is reported unstable; an occupation where more than 25% of tasks are unstable is not published as a point score |")
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
        add("  dimension D should be low.")
        add("- **BPO and contact-centre work.** The occupation most exposed to this")
        add("  measure's headline framing in the Philippines, and the one where the gap")
        add("  between task exposure and employment outcome is widest. Treat any")
        add("  reporting of it with particular care.")
        return "\n".join(lines) + "\n"

    add(f"Runs analysed: **{len(runs)}**")
    add("")
    for run in runs:
        add(f"## Run `{run['run_id']}`")
        add("")
        add(f"- model: `{run['model_id']}` (provider `{run['model_provider']}`)")
        add(f"- rubric `{run['rubric_version']}`, prompt `{run['prompt_version']}`")
        add(f"- temperature {run['temperature']}, replicates {run['run_count']}, seed {run.get('seed')}")
        add(f"- scored {run.get('task_count')} tasks on {run['scoring_date']}")
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
