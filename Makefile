# TrabahoLens v2 pipeline.
#
# Ordered as the data flows. Every target is safe to run repeatedly; none of
# them invents a value when its input is missing — they fail or record the gap.

PY := uv run python

.PHONY: help audit fetch-data validate-raw build-crosswalk build-metrics \
        build-release score-exposure sensitivity validate-release build-site \
        test test-populated-pipeline check check-stale determinism all clean-generated

help:
	@echo "TrabahoLens v2"
	@echo ""
	@echo "  make audit            Profile the archived v1 dataset -> docs/audit/"
	@echo "  make fetch-data       Attempt every registered source; record hashes and failures"
	@echo "  make validate-raw     Hash anything manually placed in data/raw/ into the manifest"
	@echo "  make build-crosswalk  Rebuild canonical tables including the PSOC crosswalk"
	@echo "  make build-metrics    Rebuild canonical tables including metric observations"
	@echo "  make score-exposure   Run the task-exposure scoring harness (needs MODEL=, a key, network)"
	@echo "  make sensitivity      Regenerate the stability and sensitivity report"
	@echo "  make build-release    Write the release manifest and the site payload"
	@echo "  make validate-release Run every release validator"
	@echo "  make build-site       build-release + validate-release"
	@echo "  make test             Run the test suite"
	@echo "  make test-populated-pipeline  Prove a populated fixture publishes end to end"
	@echo "  make check            Compile sources and validate the release"
	@echo "  make check-stale      Prove the committed artifacts match their inputs"
	@echo "  make determinism      Prove two builds are byte-identical"
	@echo "  make all              audit -> build -> validate -> test"

audit:
	$(PY) scripts/audit_baseline.py

fetch-data:
	$(PY) scripts/acquire.py

validate-raw:
	$(PY) -c "from trabaholens.v2.acquire import hash_existing_raw_files as h; \
	          rows = h(); print(f'hashed {len(rows)} raw file(s) into the retrieval manifest')"

build-crosswalk build-metrics:
	$(PY) scripts/build_canonical.py

# MODEL is required: a scoring run without a recorded model id has no provenance.
score-exposure:
ifndef MODEL
	$(error MODEL is required, e.g. `make score-exposure MODEL=anthropic/claude-3.5-haiku`)
endif
	$(PY) scripts/score_exposure.py --model "$(MODEL)" --runs $(or $(RUNS),3)

sensitivity:
	$(PY) scripts/exposure_analysis.py

build-release:
	$(PY) scripts/build_release.py --frozen-time $(or $(RELEASE_TIME),2026-09-14T00:00:00Z)

validate-release:
	$(PY) scripts/validate_release.py

build-site: build-release validate-release

test:
	uv run pytest tests/ -q

# The rest of the suite proves validators reject bad input. This target proves
# the opposite direction: that a correctly populated source actually reaches a
# published value. On an empty production dataset every other check passes
# trivially, so this is the one that shows the pipeline works.
test-populated-pipeline:
	uv run pytest tests/test_populated_pipeline.py -q

check:
	$(PY) scripts/check.py

# Build-time stamps (code_commit, release_date) are excluded: code_commit
# records HEAD, and committing the artifact moves HEAD, so a plain diff after a
# rebuild could never pass.
check-stale:
	$(PY) scripts/check_stale.py

determinism:
	@$(PY) scripts/build_release.py --frozen-time 2026-01-01T00:00:00Z >/dev/null
	@sha256sum site/data.json data/release/manifest.json > /tmp/tl-build-1.sha
	@$(PY) scripts/build_release.py --frozen-time 2026-01-01T00:00:00Z >/dev/null
	@sha256sum site/data.json data/release/manifest.json > /tmp/tl-build-2.sha
	@diff /tmp/tl-build-1.sha /tmp/tl-build-2.sha && echo "Deterministic: two builds are byte-identical."
	@$(MAKE) --no-print-directory build-release

all: audit build-metrics sensitivity build-site test check-stale

clean-generated:
	rm -rf data/raw
