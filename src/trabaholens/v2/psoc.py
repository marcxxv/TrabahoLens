"""PSOC 2012 classification structure.

The Philippine Standard Occupational Classification (PSOC) 2012 is the PSA's
national occupational classification and is built on ISCO-08. It replaces
O*NET-SOC as this project's canonical key.

## Provenance of this code list — read before using it

The authoritative PSOC 2012 volume published by the Philippine Statistics
Authority could **not be retrieved in the build environment** (the host is
blocked by network policy; see ``docs/limitations.md``). The structure below is
therefore entered from classification documentation of the ISCO-08 skeleton that
PSOC 2012 adopts, and every row is marked
``verification_status = "unverified_pending_source"``.

Two consequences, both enforced by validators rather than left to good
intentions:

1. No row may be published without that marker until someone diffs it against
   the PSA volume. ``tests/test_validation_suite.py`` fails the build otherwise.
2. PSOC 2012 is known to depart from ISCO-08 in places — the PSA adds
   Philippine-specific unit groups and renames others. Those departures are
   exactly what this list cannot yet capture, which is why it stops at
   sub-major group (2-digit) level. Minor (3-digit) and unit (4-digit) groups
   are deliberately absent rather than guessed.

Aggregate levels only, no invented detail: that is the point.
"""

from __future__ import annotations

# The current PSA publication is the 2022 Updates to the 2012 PSOC. The rows in
# this module are still the ISCO-08-aligned skeleton, so they are marked
# unverified; the version string names what they are meant to become, and
# transform.COMPATIBLE_PSOC_VERSIONS decides what may reconcile onto it.
PSOC_VERSION = "PSOC 2012 (2022 Updates)"
PSOC_SOURCE_URL = "https://psa.gov.ph/classification/psoc"
PSOC_SOURCE_ORGANIZATION = "Philippine Statistics Authority"
PSOC_SOURCE_DATASET = "2022 Updates to the 2012 Philippine Standard Occupational Classification (PSOC)"

# major code -> title
MAJOR_GROUPS: dict[str, str] = {
    "0": "Armed Forces Occupations",
    "1": "Managers",
    "2": "Professionals",
    "3": "Technicians and Associate Professionals",
    "4": "Clerical Support Workers",
    "5": "Service and Sales Workers",
    "6": "Skilled Agricultural, Forestry and Fishery Workers",
    "7": "Craft and Related Trades Workers",
    "8": "Plant and Machine Operators and Assemblers",
    "9": "Elementary Occupations",
}

# sub-major code -> title. ISCO-08 skeleton adopted by PSOC 2012.
SUB_MAJOR_GROUPS: dict[str, str] = {
    "01": "Commissioned Armed Forces Officers",
    "02": "Non-commissioned Armed Forces Officers",
    "03": "Armed Forces Occupations, Other Ranks",

    "11": "Chief Executives, Senior Officials and Legislators",
    "12": "Administrative and Commercial Managers",
    "13": "Production and Specialised Services Managers",
    "14": "Hospitality, Retail and Other Services Managers",

    "21": "Science and Engineering Professionals",
    "22": "Health Professionals",
    "23": "Teaching Professionals",
    "24": "Business and Administration Professionals",
    "25": "Information and Communications Technology Professionals",
    "26": "Legal, Social and Cultural Professionals",

    "31": "Science and Engineering Associate Professionals",
    "32": "Health Associate Professionals",
    "33": "Business and Administration Associate Professionals",
    "34": "Legal, Social, Cultural and Related Associate Professionals",
    "35": "Information and Communications Technicians",

    "41": "General and Keyboard Clerks",
    "42": "Customer Services Clerks",
    "43": "Numerical and Material Recording Clerks",
    "44": "Other Clerical Support Workers",

    "51": "Personal Service Workers",
    "52": "Sales Workers",
    "53": "Personal Care Workers",
    "54": "Protective Services Workers",

    "61": "Market-oriented Skilled Agricultural Workers",
    "62": "Market-oriented Skilled Forestry, Fishery and Hunting Workers",
    "63": "Subsistence Farmers, Fishers, Hunters and Gatherers",

    "71": "Building and Related Trades Workers, Excluding Electricians",
    "72": "Metal, Machinery and Related Trades Workers",
    "73": "Handicraft and Printing Workers",
    "74": "Electrical and Electronic Trades Workers",
    "75": "Food Processing, Woodworking, Garment and Other Craft and Related Trades Workers",

    "81": "Stationary Plant and Machine Operators",
    "82": "Assemblers",
    "83": "Drivers and Mobile Plant Operators",

    "91": "Cleaners and Helpers",
    "92": "Agricultural, Forestry and Fishery Labourers",
    "93": "Labourers in Mining, Construction, Manufacturing and Transport",
    "94": "Food Preparation Assistants",
    "95": "Street and Related Sales and Service Workers",
    "96": "Refuse Workers and Other Elementary Workers",
}

# PSOC 2012 adopts the ISCO-08 skeleton at these levels, so the codes coincide.
# Recorded explicitly so the crosswalk states its basis rather than assuming it.
ISCO08_EQUIVALENT = {code: code for code in list(MAJOR_GROUPS) + list(SUB_MAJOR_GROUPS)}


def major_of(psoc_code: str) -> str:
    return psoc_code[0]


def level_of(psoc_code: str) -> str:
    return {1: "psoc_major_group", 2: "psoc_sub_major_group"}[len(psoc_code)]


def parent_of(psoc_code: str) -> str:
    """Parent code, or empty string for a major group (which has no parent)."""
    return psoc_code[:-1] if len(psoc_code) > 1 else ""


def iter_classification_rows():
    """Yield every classification row, majors before their sub-majors."""
    for major, title in sorted(MAJOR_GROUPS.items()):
        yield {
            "psoc_code": major,
            "level": "psoc_major_group",
            "title": title,
            "parent_psoc_code": "",
            "psoc_major": major,
            "psoc_major_label": title,
        }
        for sub, sub_title in sorted(SUB_MAJOR_GROUPS.items()):
            if sub[0] != major:
                continue
            yield {
                "psoc_code": sub,
                "level": "psoc_sub_major_group",
                "title": sub_title,
                "parent_psoc_code": major,
                "psoc_major": major,
                "psoc_major_label": title,
            }


def validate_structure() -> list[str]:
    """Structural problems in the code list itself. Empty means consistent."""
    problems: list[str] = []
    for sub in SUB_MAJOR_GROUPS:
        if len(sub) != 2 or not sub.isdigit():
            problems.append(f"sub-major code is not two digits: {sub!r}")
        elif sub[0] not in MAJOR_GROUPS:
            problems.append(f"sub-major {sub} has no parent major group {sub[0]}")
    for major in MAJOR_GROUPS:
        if not any(sub[0] == major for sub in SUB_MAJOR_GROUPS):
            problems.append(f"major group {major} has no sub-major groups")
    return problems
