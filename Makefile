.PHONY: check check-data-plane check-trust check-agents check-tools check-frontend \
        ownership invariants

check:
	ruff check .
	ruff format --check .
	pytest -q

check-data-plane:
	ruff check registry ingest sim store eval fixtures tests/data_plane
	pytest -q tests/data_plane -m data_plane

check-trust:
	ruff check trust tests/trust
	pytest -q tests/trust -m trust

check-agents:
	ruff check worldstate agents graph prompts tests/agents
	pytest -q tests/agents -m agents

check-tools:
	ruff check tools schedule verify api tests/tools
	pytest -q tests/tools -m tools

check-frontend:
	cd frontend && npm run lint && npm test

ownership:
	bash scripts/check-ownership.sh

invariants:
	pytest -q tests/invariants -m invariants
