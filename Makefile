.PHONY: test smoke check

test:
	python -m unittest discover -s tests -v

smoke:
	python -m agentack demo secure
	@python -m agentack demo action-swap >/dev/null 2>&1; test $$? -eq 1

check: test smoke
