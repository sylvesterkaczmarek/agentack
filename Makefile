.PHONY: test smoke check

test:
	python -m unittest discover -s tests -v

smoke:
	python -m agentack demo secure
	@python -m agentack demo action-swap >/dev/null 2>&1; test $$? -eq 1
	@python -m agentack demo secure --write /tmp/agentack-secure.jsonl >/dev/null
	@head -n -1 /tmp/agentack-secure.jsonl > /tmp/agentack-incomplete.jsonl
	@python -m agentack check /tmp/agentack-incomplete.jsonl >/dev/null 2>&1; test $$? -eq 3

check: test smoke
