"""TrabahoLens v2: PSOC-first, provenance-carrying data layer.

The v2 package is deliberately separate from the v1 modules it replaces. v1
modules remain importable so the legacy artifacts under ``data/legacy/v1`` can
still be profiled and explained, but nothing in v2 consumes a v1 value as
evidence.
"""

V2_SCHEMA_VERSION = "2.0.0"
