"""Score each occupation's generative-AI-only exposure using OpenRouter."""

from __future__ import annotations

import argparse
import json
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

from pathlib import Path

from .pipeline_utils import DERIVED_OCCUPATIONS_CSV, DERIVED_SCORES_JSON, REPO_ROOT
from .validation import load_csv_rows

load_dotenv(REPO_ROOT / ".env")

DEFAULT_MODEL = "claude-3-5-haiku"
OUTPUT_FILE = str(DERIVED_SCORES_JSON)
VALID_RISK_VECTORS = {
    "generative_ai",
    "knowledge_work_routinization",
    "writing_automation",
    "code_generation",
    "analysis_automation",
    "minimal",
}

SYSTEM_PROMPT = """\
You are an expert labor economist specializing in generative AI and LLM automation.

Score this occupation's AI EXPOSURE from 0 to 10.

AI Exposure measures how much generative AI (LLMs, code generation, design synthesis,
writing, analysis, translation) will reshape this occupation in the Philippines over 5-10 years.

WHAT THIS DOES NOT INCLUDE:
- Autonomous vehicles or robotics (machinery automation)
- Platform algorithms and dispatch optimization (non-generative)
- Task augmentation by non-AI tools
- Demand elasticity or labor market reallocation

WHAT THIS MEASURES:
- Capability of large language models (ChatGPT, Claude, Gemini) to automate or heavily reshape core tasks
- Generative AI-driven code generation, writing, analysis, translation, design feedback
- Knowledge work where LLMs can produce work-product quality acceptable to downstream users
- Routine information processing that LLMs handle today

PHILIPPINE CONTEXT:
- OFW Channel Risk: High ofw_share means LLM adoption at destination may happen faster (for example, foreign law firms adopting AI-powered document review)
- Informal Economy: High informality slows LLM adoption (informal shops use less software)
- Infrastructure: Philippine adoption of enterprise AI follows global trends with delay
- Task Value: High-value knowledge work adopts LLMs faster than low-margin repetitive work

SCORE ANCHORS (Generative AI Only):
0-1: Minimal. Physical work, no generative AI exposure pathway (carpenter, nurse, security guard, delivery rider).
2-3: Low. Some documentation but not core value (construction supervisor, electrician, machine operator).
4-5: Moderate. Mixed routine and judgment work; LLMs assist but do not replace core (accountant, junior analyst, graphic designer).
6-7: High. Standardized knowledge work; LLMs capable of most tasks (copywriter, junior software engineer, data analyst, translator).
8-9: Very high. Routine digital processing; LLM already capable of most output (content writer, junior legal researcher, customer support analyst).
10: Maximum. Pure text-in, text-out with no domain-specific judgment (transcriptionist, basic chat support, form-filling automation).

Expected average: ~3.5-4.5 (lower than current conflated baseline of 4.5-5.0).

Respond ONLY with valid JSON:
{"exposure": <0-10 integer>, "rationale": "<2-3 sentences explaining generative AI exposure in PH context>", "primary_risk_vector": "<generative_ai|knowledge_work_routinization|writing_automation|code_generation|analysis_automation|minimal>"}
"""


def _strip_code_fences(text):
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _extract_json_object(text):
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object start found")

    depth = 0
    for idx in range(start, len(text)):
        char = text[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]

    raise ValueError("No complete JSON object found")


def _parse_model_json(raw_content):
    content = _strip_code_fences(raw_content)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        candidate = _extract_json_object(content)
        return json.loads(candidate)


def _validate_result(result):
    required = {"exposure", "rationale", "primary_risk_vector"}
    missing = required - set(result.keys())
    if missing:
        raise ValueError(f"Missing required keys: {sorted(missing)}")

    exposure = result["exposure"]
    if isinstance(exposure, bool):
        raise ValueError("Exposure cannot be boolean")
    if not isinstance(exposure, (int, float)):
        raise ValueError("Exposure must be a number")
    if int(exposure) != exposure:
        raise ValueError("Exposure must be an integer")

    exposure = int(exposure)
    if exposure < 0 or exposure > 10:
        raise ValueError("Exposure must be between 0 and 10")

    rationale = str(result["rationale"]).strip()
    if not rationale:
        raise ValueError("Rationale cannot be empty")

    risk_vector = str(result["primary_risk_vector"]).strip()
    if risk_vector not in VALID_RISK_VECTORS:
        raise ValueError(
            "primary_risk_vector must be one of "
            f"{sorted(VALID_RISK_VECTORS)}"
        )

    return {
        "exposure": exposure,
        "rationale": rationale,
        "primary_risk_vector": risk_vector,
    }


def score_occupation(client, text, model, max_attempts=3):
    """Send one occupation to Claude via OpenRouter and parse validated JSON."""
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=350,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            )
            content = response.choices[0].message.content.strip()
            parsed = _parse_model_json(content)
            return _validate_result(parsed)
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                time.sleep(min(1.5 * attempt, 4.0))

    raise RuntimeError(f"Model response failed after {max_attempts} attempts: {last_error}")


def _safe_int(value):
    if value in (None, ""):
        return None
    return int(float(value))


def _safe_float(value):
    if value in (None, ""):
        return None
    return float(value)


def _v1_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--force", action="store_true", help="Re-score even if already cached")
    parser.add_argument(
        "--output-file",
        default=OUTPUT_FILE,
        help=f"Output JSON cache file (default: {DERIVED_SCORES_JSON})",
    )
    parser.add_argument(
        "--titles-file",
        default=None,
        help="Optional newline-delimited file of occupation titles to score",
    )
    parser.add_argument(
        "--titles",
        default=None,
        help="Optional comma-delimited list of occupation titles to score",
    )
    args = parser.parse_args()

    occupations = load_csv_rows(DERIVED_OCCUPATIONS_CSV, "Occupation CSV")

    selected_titles = None
    if args.titles_file:
        with open(args.titles_file) as f:
            selected_titles = [line.strip() for line in f if line.strip()]
    elif args.titles:
        selected_titles = [item.strip() for item in args.titles.split(",") if item.strip()]

    if selected_titles is not None:
        wanted = set(selected_titles)
        occupations = [o for o in occupations if o["title"] in wanted]
        missing = [t for t in selected_titles if t not in {o["title"] for o in occupations}]
        if missing:
            print(f"Warning: some requested titles were not found in {DERIVED_OCCUPATIONS_CSV}")
            for title in missing:
                print(f"  - {title}")

    subset = occupations[args.start:args.end]

    # Load existing scores for resume support
    scores = {}
    output_path = Path(args.output_file)

    if output_path.exists() and not args.force:
        with open(output_path, encoding="utf-8") as f:
            for entry in json.load(f):
                scores[entry["title"]] = entry

    print(f"Scoring {len(subset)} occupations with {args.model}")
    print(f"Output file: {output_path}")
    print(f"Already cached: {len(scores)}")

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    errors = []
    success_count = 0
    cached_count = 0

    for i, occ in enumerate(subset):
        title = occ["title"]
        if title in scores and not args.force:
            cached_count += 1
            print(f"  [{i + 1}/{len(subset)}] {title}... cached")
            continue

        text = (
            f"title: {occ['title']}\n"
            f"psoc_label: {occ['psoc_label']}\n"
            f"category: {occ['category']}\n"
            f"employment_estimate: {_safe_int(occ['employment_estimate'])}\n"
            f"avg_monthly_wage_php: {_safe_int(occ['avg_monthly_wage_php'])}\n"
            f"education_label: {occ['education_label']}\n"
            f"ofw_share: {_safe_float(occ['ofw_share'])}\n"
            f"informal_share: {_safe_float(occ['informal_share'])}\n"
            f"description: {occ['description']}"
        )

        print(f"  [{i + 1}/{len(subset)}] {title}...", end=" ", flush=True)
        try:
            result = score_occupation(client, text, args.model, max_attempts=3)
            scores[title] = {"title": title, **result}
            success_count += 1
            print(
                "exposure="
                f"{result['exposure']}"
                f", vector={result['primary_risk_vector']}"
            )
        except Exception as exc:
            print(f"ERROR: {exc}")
            errors.append(title)

        # Incremental checkpoint after each occupation for resumability
        ordered = []
        for record in occupations:
            record_title = record["title"]
            if record_title in scores:
                ordered.append(scores[record_title])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file_handle:
            json.dump(ordered, file_handle, indent=2, ensure_ascii=False)

        if i < len(subset) - 1:
            time.sleep(args.delay)

    scored_vals = [s for s in scores.values() if "exposure" in s]
    avg = None
    if scored_vals:
        avg = sum(s["exposure"] for s in scored_vals) / len(scored_vals)

    print("\nRun summary")
    print(f"  success_count: {success_count}")
    print(f"  cached_count: {cached_count}")
    print(f"  error_count: {len(errors)}")
    print(f"  total_in_output: {len(scores)}")
    if avg is not None:
        print(f"  average_exposure: {avg:.2f}")
    if errors:
        print("  failed_titles:")
        for title in errors:
            print(f"    - {title}")


_RETIRED = (
    "{name} is a TrabahoLens v1 module, retired by the credibility rebuild.\n"
    "It is kept readable because docs/audit/baseline-audit.md cites it line by\n"
    "line, but it must not run: it would regenerate values the audit found to be\n"
    "synthetic, constant-by-category or placeholder.\n"
    "See docs/migration-notes.md. Use the v2 pipeline: `make help`."
)


def main(*_args, **_kwargs):  # noqa: D401 - retired entry point
    raise SystemExit(_RETIRED.format(name=__name__))
