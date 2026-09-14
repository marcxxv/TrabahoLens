"""Forensic profiler for the archived TrabahoLens v1 artifacts.

Writes ``docs/audit/current-data-profile.json``. Every number in
``docs/audit/baseline-audit.md`` comes from this file, so the audit can be
re-derived rather than trusted.

The profiler reads only from ``data/legacy/v1/`` so that it keeps working after
the v1 pipeline outputs are withdrawn from ``data/derived/``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .paths import (
    AUDIT_DIR,
    LEGACY_DIR,
    LEGACY_OCCUPATIONS_CSV,
    LEGACY_SCORES_JSON,
    LEGACY_SEED_JSON,
    LEGACY_SITE_DATA_JSON,
    REPO_ROOT,
    ensure_parent,
    rel,
)

PROFILE_JSON = AUDIT_DIR / "current-data-profile.json"

# Numeric fields in the published v1 site dataset, and the v1 code path that
# produced each one. Referenced by the audit narrative.
V1_FIELD_PRODUCERS = {
    "jobs": "assign_ph_stats.allocate_group_employment (GROUP_TOTALS split by TITLE_SIZE_MULTIPLIERS)",
    "pay": "pipeline_utils.wage_for_occupation (constant per category)",
    "outlook": "assign_ph_stats.build_stats (literal 50)",
    "education": "fetch_onet.parse_job_zones (US O*NET Job Zone)",
    "exposure": "score_ai_only.score_occupation (single LLM run)",
    "ofw_share": "pipeline_utils.PSOC_OFW_SHARE (constant per PSOC major group)",
    "informal_share": "pipeline_utils.INFORMAL_SHARE_BY_CATEGORY (constant per category)",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:  # pragma: no cover - only when git is unavailable
        return "unknown"


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def profile_numeric(values: list[Any]) -> dict[str, Any]:
    """Distribution summary that makes constant-fill and low cardinality visible."""
    numbers = [n for n in (_num(v) for v in values) if n is not None]
    nulls = len(values) - len(numbers)
    counter = Counter(numbers)
    summary: dict[str, Any] = {
        "count": len(values),
        "non_null": len(numbers),
        "null": nulls,
        "distinct": len(counter),
    }
    if not numbers:
        return summary
    ordered = sorted(numbers)
    summary.update(
        {
            "min": ordered[0],
            "max": ordered[-1],
            "median": ordered[len(ordered) // 2],
            "mean": round(sum(ordered) / len(ordered), 6),
            "zero_or_negative": sum(1 for n in numbers if n <= 0),
            "most_common": [
                {"value": value, "n": n, "share_of_rows": round(n / len(values), 4)}
                for value, n in counter.most_common(5)
            ],
            # A single value covering most rows is the fingerprint of a constant
            # assigned to a whole category rather than an observation.
            "max_repeat_share": round(counter.most_common(1)[0][1] / len(values), 4),
        }
    )
    return summary


def profile_site_data(records: list[dict]) -> dict[str, Any]:
    numeric_fields = ["pay", "jobs", "outlook", "education", "exposure", "ofw_share", "informal_share"]
    fields = {field: profile_numeric([r.get(field) for r in records]) for field in numeric_fields}

    for field, summary in fields.items():
        summary["v1_code_path"] = V1_FIELD_PRODUCERS.get(field, "unknown")
        summary["is_universal_constant"] = summary.get("distinct") == 1

    by_group: dict[str, dict[str, Any]] = {}
    grouped = defaultdict(list)
    for record in records:
        grouped[str(record.get("psoc_major"))].append(record)
    for major, group in sorted(grouped.items()):
        by_group[major] = {
            "label": group[0].get("psoc_label"),
            "occupations": len(group),
            "employment_sum": sum(int(r["jobs"]) for r in group if r.get("jobs")),
            "distinct_wages": len({r.get("pay") for r in group}),
            "distinct_ofw_shares": len({r.get("ofw_share") for r in group}),
            "distinct_informal_shares": len({r.get("informal_share") for r in group}),
        }

    titles = [r.get("title") for r in records]
    normalised = [str(t).strip().lower() for t in titles]

    total_employment = sum(int(r["jobs"]) for r in records if r.get("jobs"))
    payroll = sum(int(r["jobs"]) * int(r["pay"]) for r in records if r.get("jobs") and r.get("pay"))

    return {
        "records": len(records),
        "fields_present": sorted({key for record in records for key in record}),
        "numeric_field_profiles": fields,
        "duplicate_titles": [t for t, n in Counter(titles).items() if n > 1],
        "title_normalisation_collisions": [t for t, n in Counter(normalised).items() if n > 1],
        "by_psoc_major": by_group,
        "psoc_majors_present": sorted(grouped, key=lambda m: int(m)),
        "derived_headlines": {
            "total_employment_published": total_employment,
            "implied_monthly_payroll_php": payroll,
            "note": (
                "Both headline aggregates are products of synthetic inputs: employment "
                "is a hard-coded group total split by title keyword multipliers, and pay "
                "is a constant per category."
            ),
        },
        "source_field_counts": dict(Counter(r.get("source") for r in records)),
    }


def profile_group_total_reconciliation(records: list[dict]) -> dict[str, Any]:
    """Check published group sums against the v1 hard-coded GROUP_TOTALS."""
    from ..assign_ph_stats import GROUP_TOTALS

    published: dict[int, int] = defaultdict(int)
    for record in records:
        if record.get("jobs"):
            published[int(record["psoc_major"])] += int(record["jobs"])

    rows = []
    for major in sorted(set(GROUP_TOTALS) | set(published)):
        declared = GROUP_TOTALS.get(major)
        actual = published.get(major, 0)
        rows.append(
            {
                "psoc_major": major,
                "hard_coded_group_total": declared,
                "published_sum": actual,
                "difference": None if declared is None else actual - declared,
                "reconciles": declared is not None and actual == declared,
            }
        )
    return {
        "hard_coded_total_all_groups": sum(GROUP_TOTALS.values()),
        "published_total_all_groups": sum(published.values()),
        "per_group": rows,
        "groups_that_do_not_reconcile": [r["psoc_major"] for r in rows if not r["reconciles"]],
    }


def profile_scores(scores: list[dict]) -> dict[str, Any]:
    exposures = [s.get("exposure") for s in scores]
    provenance_fields = [
        "rubric_version",
        "prompt_version",
        "model_provider",
        "model_id",
        "scoring_date",
        "temperature",
        "run_count",
        "aggregation_method",
        "uncertainty_or_stability",
        "human_review_status",
        "raw_response_reference",
    ]
    present = sorted({key for score in scores for key in score})
    return {
        "records": len(scores),
        "fields_present": present,
        "exposure_distribution": profile_numeric(exposures),
        "primary_risk_vector_counts": dict(Counter(s.get("primary_risk_vector") for s in scores)),
        "provenance_fields_missing": [f for f in provenance_fields if f not in present],
        "has_any_model_provenance": any(f in present for f in provenance_fields),
        "duplicate_titles": [t for t, n in Counter(s.get("title") for s in scores).items() if n > 1],
    }


def profile_crosswalk(rows: list[dict]) -> dict[str, Any]:
    """v1 had no crosswalk table; the mapping lived in a SOC-major dict."""
    from ..pipeline_utils import SOC_TO_PSOC_MAJOR

    inverse = defaultdict(list)
    for soc_major, psoc_major in SOC_TO_PSOC_MAJOR.items():
        inverse[psoc_major].append(soc_major)

    soc_majors_in_data = Counter()
    for row in rows:
        code = row.get("soc_code", "")
        if code and not code.startswith("PH-") and "-" in code:
            soc_majors_in_data[code.split("-")[0]] += 1

    return {
        "crosswalk_table_exists": False,
        "mapping_mechanism": "pipeline_utils.SOC_TO_PSOC_MAJOR (US SOC 2-digit major -> PSOC major group)",
        "match_type_recorded": False,
        "match_quality_recorded": False,
        "mapping_basis_recorded": False,
        "review_status_recorded": False,
        "distinct_soc_majors_mapped": len(SOC_TO_PSOC_MAJOR),
        "many_to_one_targets": {
            str(psoc): sorted(soc)
            for psoc, soc in sorted(inverse.items())
            if len(soc) > 1
        },
        "psoc_majors_reachable_from_soc": sorted(set(SOC_TO_PSOC_MAJOR.values())),
        "psoc_majors_unreachable_from_soc": sorted(set(range(1, 10)) - set(SOC_TO_PSOC_MAJOR.values())),
        "soc_majors_present_in_published_rows": dict(sorted(soc_majors_in_data.items())),
    }


def profile_overlap(records: list[dict]) -> dict[str, Any]:
    """Aggregate/component overlap and double-count candidates.

    v1 mixed granular O*NET detailed occupations with hand-written broad
    Philippine categories inside the same employment total, so their employment
    counts are not additive.
    """
    ph_native = [r for r in records if r.get("source") == "ph_native"]
    onet = [r for r in records if r.get("source") == "onet"]

    overlaps = []
    ph_terms = {
        "Kasambahay (domestic workers)": ["maid", "housekeep", "domestic"],
        "Tricycle / jeepney drivers": ["driver", "taxi", "bus", "chauffeur"],
        "Delivery riders": ["delivery", "courier", "driver"],
        "Barangay health workers": ["health", "community health"],
        "Seafarers / merchant marine": ["sailor", "marine", "ship", "vessel", "captain"],
        "OFW caregivers": ["care", "personal care", "home health"],
        "Street vendors / market sellers": ["vendor", "sales", "cashier", "retail"],
        "Hairdressers and beauty workers": ["hairdress", "barber", "cosmet", "skincare"],
        "Agricultural farm laborers": ["farmworker", "agricultural", "farm", "crop"],
        "Fisherfolk": ["fish"],
    }
    for record in ph_native:
        terms = ph_terms.get(record["title"], [])
        matches = [
            o["title"]
            for o in onet
            if any(term in str(o["title"]).lower() for term in terms)
        ]
        if matches:
            overlaps.append(
                {
                    "ph_record": record["title"],
                    "ph_employment": record.get("jobs"),
                    "overlapping_onet_titles": sorted(matches),
                    "overlapping_onet_employment": sum(
                        int(o["jobs"]) for o in onet if o["title"] in matches and o.get("jobs")
                    ),
                }
            )

    return {
        "ph_native_records": len(ph_native),
        "onet_records": len(onet),
        "ph_records_with_overlapping_onet_titles": len(overlaps),
        "overlap_detail": overlaps,
        "note": (
            "Both sets share a single employment budget per PSOC major group, so the "
            "published per-occupation employment for overlapping concepts is neither "
            "independent nor additive."
        ),
    }


def profile_ofw_denominator_test(records: list[dict]) -> dict[str, Any]:
    """Decide empirically whether v1's ``ofw_share`` is P(OFW|occupation) or P(occupation|OFW).

    A genuine "share of workers in this group who are OFWs" is a set of
    independent ratios with no reason to sum to 1. A "distribution of OFWs
    across occupation groups" must sum to 1. v1 assigns one constant per PSOC
    major group, so summing the distinct constants is a direct test.
    """
    per_major: dict[int, set[float]] = defaultdict(set)
    for record in records:
        value = _num(record.get("ofw_share"))
        if value is not None:
            per_major[int(record["psoc_major"])].add(value)

    constants = {major: sorted(values) for major, values in sorted(per_major.items())}
    single_valued = all(len(values) == 1 for values in constants.values())
    total = round(sum(values[0] for values in constants.values()), 4) if single_valued else None

    return {
        "constant_per_psoc_major": single_valued,
        "value_by_psoc_major": {str(k): v[0] if len(v) == 1 else v for k, v in constants.items()},
        "sum_of_group_constants": total,
        "sums_to_one_within_tolerance": total is not None and abs(total - 1.0) <= 0.05,
        "interpretation": (
            "The nine group constants sum to ~1.0, which is the signature of a "
            "distribution of OFWs across occupation groups, P(occupation | OFW). "
            "v1 displays it as the share of an occupation's workers who are OFWs, "
            "P(OFW | occupation). These are different quantities and the published "
            "label is wrong."
            if (total is not None and abs(total - 1.0) <= 0.05)
            else "Group constants do not sum to 1; re-examine before concluding."
        ),
    }


def profile_repeated_value_clusters(records: list[dict]) -> dict[str, Any]:
    """Groups of occupations sharing one identical employment value.

    Identical employment across many distinct occupations cannot arise from
    observation; it is the fingerprint of a budget split by equal weights.
    """
    clusters: dict[float, list[str]] = defaultdict(list)
    for record in records:
        value = _num(record.get("jobs"))
        if value is not None:
            clusters[value].append(str(record.get("title")))

    repeated = [
        {
            "employment_value": int(value),
            "occupations": len(titles),
            "example_titles": sorted(titles)[:5],
        }
        for value, titles in sorted(clusters.items(), key=lambda kv: -len(kv[1]))
        if len(titles) > 1
    ]
    rows_in_clusters = sum(item["occupations"] for item in repeated)
    return {
        "distinct_repeated_values": len(repeated),
        "rows_sharing_a_repeated_employment_value": rows_in_clusters,
        "share_of_published_rows": round(rows_in_clusters / len(records), 4) if records else 0,
        "clusters": repeated[:15],
    }


def profile_us_specific_concentration(records: list[dict]) -> dict[str, Any]:
    """How much published Philippine employment sits on US-shaped title sets."""
    patterns = {
        "postsecondary_teacher_specialisations": "postsecondary",
        "us_style_first_line_supervisors": "first-line supervisor",
    }
    out = {}
    total_employment = sum(int(r["jobs"]) for r in records if r.get("jobs")) or 1
    for name, needle in patterns.items():
        matched = [r for r in records if needle in str(r.get("title", "")).lower()]
        employment = sum(int(r["jobs"]) for r in matched if r.get("jobs"))
        out[name] = {
            "occupations": len(matched),
            "employment_assigned": employment,
            "share_of_published_employment": round(employment / total_employment, 4),
            "distinct_employment_values": len({r.get("jobs") for r in matched}),
        }
    return out


def profile_determinism() -> dict[str, Any]:
    """Can the published dataset be regenerated from committed inputs?"""
    from ..pipeline_utils import (
        DERIVED_ONET_OCCUPATIONS_JSON,
        DERIVED_PH_OCCUPATIONS_JSON,
        DERIVED_PH_OCCUPATIONS_WITH_STATS_JSON,
    )

    intermediates = {
        rel(path): path.exists()
        for path in (
            DERIVED_ONET_OCCUPATIONS_JSON,
            DERIVED_PH_OCCUPATIONS_JSON,
            DERIVED_PH_OCCUPATIONS_WITH_STATS_JSON,
        )
    }
    return {
        "committed_intermediates": intermediates,
        "all_intermediates_present": all(intermediates.values()),
        "rebuild_requires_network": True,
        "rebuild_blockers": [
            "fetch_onet downloads https://www.onetcenter.org/dl_files/database/db_30_2_text.zip",
            "the three intermediates above are .gitignored, so a clean checkout cannot "
            "reproduce data/derived/occupations_ph.csv without network access",
            "score_ai_only requires OPENROUTER_API_KEY and a live model endpoint",
        ],
        "llm_scoring_is_reproducible": False,
        "llm_scoring_notes": "temperature=0.2, single run, no seed, no raw responses retained",
    }


def build_profile() -> dict[str, Any]:
    site_records = json.loads(LEGACY_SITE_DATA_JSON.read_text(encoding="utf-8"))
    with open(LEGACY_OCCUPATIONS_CSV, encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    scores = json.loads(LEGACY_SCORES_JSON.read_text(encoding="utf-8"))
    seed = json.loads(LEGACY_SEED_JSON.read_text(encoding="utf-8"))

    files = {}
    for path in sorted(LEGACY_DIR.glob("*")):
        if path.is_file():
            files[rel(path)] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}

    seed_titles = {str(s.get("title", "")).strip().lower() for s in seed}
    csv_titles = {str(r.get("title", "")).strip().lower() for r in csv_rows}

    return {
        "profile_schema": "trabaholens-audit-profile/1",
        "repository_commit": git_commit(),
        "generated_by": "src/trabaholens/v2/audit_baseline.py",
        "inputs": files,
        "record_counts": {
            "data/legacy/v1/occupations_seed.json": len(seed),
            "data/legacy/v1/occupations_ph.csv": len(csv_rows),
            "data/legacy/v1/scores_ai_only.json": len(scores),
            "data/legacy/v1/site_data.json": len(site_records),
        },
        "published_dataset": profile_site_data(site_records),
        "group_total_reconciliation": profile_group_total_reconciliation(site_records),
        "exposure_scores": profile_scores(scores),
        "crosswalk": profile_crosswalk(csv_rows),
        "aggregate_component_overlap": profile_overlap(site_records),
        "ofw_share_denominator_test": profile_ofw_denominator_test(site_records),
        "repeated_value_clusters": profile_repeated_value_clusters(site_records),
        "us_specific_concentration": profile_us_specific_concentration(site_records),
        "determinism": profile_determinism(),
        "seed_vs_published": {
            "seed_records": len(seed),
            "published_records": len(site_records),
            "seed_titles_retained_in_published": len(seed_titles & csv_titles),
            "seed_titles_dropped": sorted(seed_titles - csv_titles),
            "published_titles_not_in_seed": len(csv_titles - seed_titles),
        },
    }


def main() -> None:
    profile = build_profile()
    ensure_parent(PROFILE_JSON)
    PROFILE_JSON.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    published = profile["published_dataset"]
    print(f"Wrote {rel(PROFILE_JSON)}")
    print(f"  published records: {published['records']}")
    constants = [f for f, s in published["numeric_field_profiles"].items() if s["is_universal_constant"]]
    print(f"  universal-constant fields: {constants or 'none'}")
    print(f"  groups that do not reconcile: {profile['group_total_reconciliation']['groups_that_do_not_reconcile']}")
    print(f"  score provenance fields missing: {len(profile['exposure_scores']['provenance_fields_missing'])}")
    ofw = profile["ofw_share_denominator_test"]
    print(f"  ofw group constants sum to: {ofw['sum_of_group_constants']} "
          f"(distribution, not share: {ofw['sums_to_one_within_tolerance']})")
    clusters = profile["repeated_value_clusters"]
    print(f"  rows sharing a repeated employment value: "
          f"{clusters['rows_sharing_a_repeated_employment_value']} of {profile['published_dataset']['records']}")


if __name__ == "__main__":
    main()
