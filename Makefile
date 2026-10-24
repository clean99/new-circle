PYTHON ?= python3
RUFF ?= $(shell command -v ruff 2>/dev/null || echo .venv/bin/ruff)
DIST := dist/anchor-training.zip

.PHONY: lint test check package

lint:
	$(RUFF) check scripts tests
	$(PYTHON) scripts/check_skill.py

test:
	$(PYTHON) -m unittest discover -s tests -v

check: lint test

package:
	rm -rf dist/anchor-training $(DIST)
	mkdir -p dist/anchor-training/scripts
	cp -R SKILL.md references templates schema dist/anchor-training/
	cp -R scripts/anchor.py scripts/anchor_core dist/anchor-training/scripts/
	find dist/anchor-training -name '__pycache__' -prune -exec rm -rf {} +
	cd dist && zip -qr anchor-training.zip anchor-training
	@echo "$(DIST)"
