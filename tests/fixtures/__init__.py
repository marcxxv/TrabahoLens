"""Synthetic fixtures for end-to-end pipeline tests.

Every number here is invented and obviously so. Fixtures live under
``tests/fixtures`` and are never reachable from a production build: the
canonical builder reads ``data/sources/retrieval-manifest.json``, and these
tests point it at a temporary manifest instead.

The values are deliberately implausible as Philippine labour statistics
(round numbers, tiny magnitudes) so that a fixture leaking into a real release
would be obvious to a reader rather than passing as data.
"""
