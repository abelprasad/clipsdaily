.PHONY: install install-dev test lint check docs deploy deploy-live clean

PY ?= python3

# Editable install from this checkout (deps already installed by setup.sh).
install:
	$(PY) -m pip install -e .

# Fast editable install without reinstalling heavy deps (torch etc).
install-dev:
	$(PY) -m pip install --no-deps -e .

# Full end-to-end smoke test against a scratch runtime home.
# Needs the package installed (make install) and network (streamlink).
test:
	bash test_e2e.sh

# Compile everything + the secret scan. Fast; run before every commit.
lint:
	$(PY) -m compileall -q src
	bash scripts/check-secrets.sh

# VERSION file must match the package version.
check:
	@test "$$(cat VERSION)" = "$$(grep -m1 '__version__' src/clipsdaily/__init__.py | sed 's/.*"\([^"]*\)".*/\1/')" || (echo "VERSION file != src/clipsdaily/__init__.py" >&2; exit 1)
	@echo "version OK: $$(cat VERSION)"

# Regenerate docs/cli-reference.md from the real CLI help.
docs:
	bash scripts/gen-cli-reference.sh

# Dry-run deploy: shows exactly what would be copied and restarted.
deploy:
	bash deploy.sh --dry-run

# Live deploy to /home/abel/clipsdaily on indra (operator machine only).
deploy-live:
	bash deploy.sh

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info src/*.egg-info
