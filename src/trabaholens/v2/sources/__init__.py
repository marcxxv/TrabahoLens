"""Source-specific parsers.

Each parser turns one verified raw snapshot into **normalised source rows** — a
flat, typed representation of what that source actually says, with its own
classification codes and its own reference period, before any mapping to PSOC or
any transformation into a canonical observation.

Keeping this stage separate matters: a parse failure and a transformation
failure have different causes and different fixes, and collapsing them is how a
pipeline starts guessing.

None of these parsers has processed its real source. Every one is fixture-tested
only, because no source could be retrieved in this environment.
"""

from .base import (
    FormatValidationError,
    NormalisedRow,
    ParseResult,
    SourceParser,
    get_parser,
    register,
    registered_parsers,
)

__all__ = [
    "FormatValidationError",
    "NormalisedRow",
    "ParseResult",
    "SourceParser",
    "get_parser",
    "register",
    "registered_parsers",
]
