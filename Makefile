PY ?= python

.PHONY: install lint fmt test clean bank discover replay reliability

install:
	$(PY) -m pip install -r requirements.txt && $(PY) -m playwright install chromium

lint:
	$(PY) -m ruff check . && $(PY) -m black --check .

fmt:
	$(PY) -m ruff check --fix . && $(PY) -m black .

# pytest exits 5 when zero tests are collected — that's expected pre-Day-1
# and must not fail CI, so it's treated as success; any other nonzero exit
# (failures, errors) still fails the build.
test:
	$(PY) -m pytest; code=$$?; if [ $$code -eq 5 ]; then exit 0; else exit $$code; fi

# Never removes artifacts/ or evidence/ — those are committed deliverables.
clean:
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null; \
	rm -rf .pytest_cache .ruff_cache

bank:
	@echo "not implemented"

discover:
	@echo "not implemented"

replay:
	@echo "not implemented"

reliability:
	@echo "not implemented"
