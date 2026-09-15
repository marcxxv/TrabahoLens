"""PSOC to O*NET-SOC crosswalk, via the intermediate classifications.

A task-first exposure score needs a defensible path from a PSOC unit to a set of
O*NET task statements. v1 had a bare dict mapping US SOC major groups onto PSOC
major groups, with no match type, quality, basis or review — correctly rejected.

The path this module models, with **every intermediate preserved** so a reviewer
can see where quality was lost:

    PSOC ──published correspondence──▶ ISCO-08
    ISCO-08 ──published correspondence──▶ US SOC
    US SOC ──structural──▶ O*NET-SOC

Each hop records its own match type, quality, basis and review status. The
composed edge is only as good as its weakest hop, and a hop with no defensible
match ends the chain rather than degrading it quietly.

Title similarity may **propose** a candidate. It can never authorise
publication: a proposal enters with ``review_status = machine_proposed`` and
``mapping_basis = title_similarity_only``, and the release validator already
refuses to publish through a title-similarity mapping that is not marked
rejected.

None of the published correspondences could be retrieved in this environment, so
the composer is fixture-tested only and no real chain exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .pipeline import StageStatus

#: Worst-to-best. Composing two hops takes the worse of the two.
MATCH_TYPE_RANK = {
    "no_defensible_match": 0,
    "composite": 1,
    "broader": 2,
    "narrower": 2,
    "close": 3,
    "exact": 4,
}
QUALITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
RANK_QUALITY = {v: k for k, v in QUALITY_RANK.items()}
RANK_MATCH = {4: "exact", 3: "close", 2: "broader", 1: "composite", 0: "no_defensible_match"}

#: A basis that may never by itself authorise a published mapping.
UNPUBLISHABLE_BASES = {"title_similarity_only", "undocumented_heuristic"}


@dataclass(frozen=True)
class CrosswalkEdge:
    """One hop between two classifications."""

    from_system: str
    from_code: str
    to_system: str
    to_code: str
    match_type: str
    match_quality: str
    mapping_basis: str
    review_status: str = "unreviewed"
    notes: str = ""

    @property
    def usable(self) -> bool:
        return (
            self.match_type != "no_defensible_match"
            and self.match_quality != "none"
            and self.review_status != "rejected"
        )


@dataclass
class ComposedMapping:
    """A full PSOC -> O*NET-SOC chain, with its intermediates kept."""

    psoc_code: str
    onet_code: str
    hops: list[CrosswalkEdge] = field(default_factory=list)
    resolution: str = "resolved"
    notes: str = ""

    @property
    def intermediate_codes(self) -> list[str]:
        return [f"{hop.to_system}:{hop.to_code}" for hop in self.hops[:-1]]

    @property
    def match_type(self) -> str:
        if not self.hops:
            return "no_defensible_match"
        return RANK_MATCH[min(MATCH_TYPE_RANK.get(h.match_type, 0) for h in self.hops)]

    @property
    def match_quality(self) -> str:
        if not self.hops:
            return "none"
        return RANK_QUALITY[min(QUALITY_RANK.get(h.match_quality, 0) for h in self.hops)]

    @property
    def mapping_basis(self) -> str:
        """The weakest basis in the chain — a chain is not stronger than its worst link."""
        for hop in self.hops:
            if hop.mapping_basis in UNPUBLISHABLE_BASES:
                return hop.mapping_basis
        bases = {hop.mapping_basis for hop in self.hops}
        if "published_correspondence" in bases and len(bases) == 1:
            return "published_correspondence"
        return "definition_review" if "definition_review" in bases else "structural_derivation"

    @property
    def review_status(self) -> str:
        if any(h.review_status == "rejected" for h in self.hops):
            return "rejected"
        if all(h.review_status == "human_reviewed" for h in self.hops) and self.hops:
            return "human_reviewed"
        return "machine_proposed"

    @property
    def publishable(self) -> bool:
        return (
            self.resolution == "resolved"
            and all(hop.usable for hop in self.hops)
            and self.mapping_basis not in UNPUBLISHABLE_BASES
            and self.review_status != "rejected"
        )

    def as_row(self, crosswalk_id: str) -> dict:
        return {
            "crosswalk_id": crosswalk_id,
            "psoc_code": self.psoc_code,
            "source_code": self.onet_code,
            "source_classification": "O*NET-SOC",
            "match_type": self.match_type,
            "match_quality": self.match_quality,
            "mapping_basis": self.mapping_basis,
            "review_status": self.review_status,
            "intermediate_codes": " -> ".join(self.intermediate_codes),
            "hop_count": len(self.hops),
            "resolution": self.resolution,
            "publishable": "true" if self.publishable else "false",
            "notes": self.notes,
        }


def compose(
    psoc_code: str,
    psoc_to_isco: Iterable[CrosswalkEdge],
    isco_to_soc: Iterable[CrosswalkEdge],
    soc_to_onet: Iterable[CrosswalkEdge],
) -> list[ComposedMapping]:
    """Walk PSOC -> ISCO -> SOC -> O*NET, refusing to resolve ambiguity silently.

    A one-to-many hop does not pick a winner. Every branch is returned, and a
    PSOC code that reaches more than one O*NET code is marked ``ambiguous`` so a
    reviewer decides rather than the code.
    """
    isco_edges = [e for e in psoc_to_isco if e.from_code == psoc_code]
    if not isco_edges:
        return [
            ComposedMapping(
                psoc_code=psoc_code, onet_code="", resolution="unmatched",
                notes="No PSOC->ISCO correspondence for this code.",
            )
        ]

    results: list[ComposedMapping] = []
    for isco_edge in isco_edges:
        if not isco_edge.usable:
            results.append(
                ComposedMapping(
                    psoc_code=psoc_code, onet_code="", hops=[isco_edge],
                    resolution="unmatched",
                    notes=f"PSOC->ISCO hop unusable ({isco_edge.match_type}/{isco_edge.match_quality}).",
                )
            )
            continue
        soc_edges = [e for e in isco_to_soc if e.from_code == isco_edge.to_code]
        if not soc_edges:
            results.append(
                ComposedMapping(
                    psoc_code=psoc_code, onet_code="", hops=[isco_edge],
                    resolution="unmatched",
                    notes=f"No ISCO->SOC correspondence for {isco_edge.to_code}.",
                )
            )
            continue
        for soc_edge in soc_edges:
            onet_edges = [e for e in soc_to_onet if e.from_code == soc_edge.to_code]
            if not onet_edges:
                results.append(
                    ComposedMapping(
                        psoc_code=psoc_code, onet_code="", hops=[isco_edge, soc_edge],
                        resolution="unmatched",
                        notes=f"No SOC->O*NET correspondence for {soc_edge.to_code}.",
                    )
                )
                continue
            for onet_edge in onet_edges:
                results.append(
                    ComposedMapping(
                        psoc_code=psoc_code,
                        onet_code=onet_edge.to_code,
                        hops=[isco_edge, soc_edge, onet_edge],
                    )
                )

    resolved = [r for r in results if r.resolution == "resolved"]
    if len(resolved) > 1:
        for mapping in resolved:
            mapping.resolution = "ambiguous"
            mapping.notes = (
                f"PSOC {psoc_code} reaches {len(resolved)} O*NET codes through this chain. "
                "Not resolved automatically; a reviewer must choose or reject."
            )
    return results


def coverage_report(mappings: list[ComposedMapping], all_psoc_codes: Iterable[str]) -> dict:
    """What the crosswalk actually covers, and what it does not.

    Required by finding 6. Reports high-quality, ambiguous, unmatched and
    excluded-from-scoring separately, because they need different work.
    """
    by_code: dict[str, list[ComposedMapping]] = {}
    for mapping in mappings:
        by_code.setdefault(mapping.psoc_code, []).append(mapping)

    high, ambiguous, unmatched, excluded = [], [], [], []
    for code in sorted(set(all_psoc_codes)):
        entries = by_code.get(code, [])
        if not entries or all(e.resolution == "unmatched" for e in entries):
            unmatched.append(code)
        elif any(e.resolution == "ambiguous" for e in entries):
            ambiguous.append(code)
        elif any(e.publishable and e.match_quality == "high" for e in entries):
            high.append(code)
        else:
            excluded.append(code)

    total = len(set(all_psoc_codes)) or 1
    return {
        "psoc_units_total": len(set(all_psoc_codes)),
        "high_quality_mappings": high,
        "ambiguous_mappings": ambiguous,
        "unmatched_philippine_specific": unmatched,
        "excluded_from_exposure_scoring": sorted(set(ambiguous) | set(unmatched) | set(excluded)),
        "coverage_share_high_quality": round(len(high) / total, 4),
        "note": (
            "An occupation whose mapping is rejected, ambiguous or unresolved is "
            "not scored. Partial coverage is disclosed rather than filled in."
        ),
    }


#: No published correspondence has been retrieved, so no real chain exists.
CROSSWALK_STAGE_STATUS = StageStatus.FIXTURE_TESTED_ONLY
