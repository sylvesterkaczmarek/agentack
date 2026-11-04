.PHONY: test smoke lint typecheck check build package-check release-check

test:
	python -m unittest discover -s tests -v

smoke:
	python scripts/smoke.py

lint:
	python -m ruff check .

typecheck:
	python -m mypy src/agentack

check: lint typecheck test smoke
	python scripts/verify_corpus.py

build:
	rm -rf build dist
	python -m build

package-check:
	python -m twine check dist/*

release-check: check build package-check
