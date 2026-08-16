"""Static safety contract for the local PostgreSQL Compose service."""

from pathlib import Path

import pytest

COMPOSE_FILE = Path(__file__).parents[2] / "store" / "docker-compose.yml"


@pytest.mark.data_plane
def test_local_postgres_is_loopback_only_and_persistent():
    compose = COMPOSE_FILE.read_text()

    assert '"127.0.0.1:${POSTGRES_PORT:-54322}:5432"' in compose
    assert "farmops_postgres_data:/var/lib/postgresql/data" in compose
    assert "./schema.sql:/docker-entrypoint-initdb.d/001-schema.sql:ro" in compose


@pytest.mark.data_plane
def test_local_postgres_has_healthcheck_and_non_production_defaults():
    compose = COMPOSE_FILE.read_text()

    assert "pg_isready" in compose
    assert "POSTGRES_DB: ${POSTGRES_DB:-farmops}" in compose
    assert "POSTGRES_USER: ${POSTGRES_USER:-farmops}" in compose
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-farmops_dev}" in compose
