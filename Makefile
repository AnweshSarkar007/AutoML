PY ?= python

.PHONY: install lint fmt test clean bank discover replay reliability

install:
	$(PY) -m pip install -r requirements.txt && $(PY) -m playwright install chromium

lint:
	$(PY) -m ruff check . && $(PY) -m black --check .

fmt:
	$(PY) -m ruff check --fix . && $(PY) -m black .

test:
	$(PY) -m pytest

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
