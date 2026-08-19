.PHONY: test smoke lint typecheck check build package-check release-check

test:
	python -m unittest discover -s tests -v

smoke:
	python -m agentack demo
	python -m agentack doctor
	python -m agentack coverage
	python -m agentack demo secure
	@python -m agentack demo action-swap >/dev/null 2>&1; test $$? -eq 1
	@python -m agentack demo secure --write /tmp/agentack-secure.jsonl >/dev/null
	@head -n -1 /tmp/agentack-secure.jsonl > /tmp/agentack-incomplete.jsonl
	@python -m agentack check /tmp/agentack-incomplete.jsonl >/dev/null 2>&1; test $$? -eq 3

lint:
	python -m ruff check .

typecheck:
	python -m mypy src/agentack/models.py src/agentack/provenance.py src/agentack/report.py src/agentack/adapters/base.py

check: lint typecheck test smoke

build:
	rm -rf build dist
	python -m build

package-check:
	python -m twine check dist/*

release-check: check build package-check
