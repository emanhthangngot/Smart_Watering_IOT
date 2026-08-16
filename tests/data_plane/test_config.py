"""LLM provider config additions for coordination gate C5: fail-closed
enable check and secret redaction from repr/str."""

from __future__ import annotations

import pytest

from config import Config

pytestmark = pytest.mark.data_plane


def _config(**overrides) -> Config:
    values = {
        "team_code": "VAMOS",
        "environment": "FARM",
        "actuation_target": "none",
        "mqtt_host": "",
        "mqtt_port": 443,
        "mqtt_username": "",
        "mqtt_password": "mqtt-secret",
        "mqtt_client_id": "",
        "mqtt_topic": "",
        "supabase_url": "",
        "supabase_service_role_key": "supabase-secret",
        "operator_token": "operator-secret",
    }
    values.update(overrides)
    return Config(**values)


def test_llm_disabled_by_default():
    assert _config().llm_enabled is False


def test_llm_enabled_requires_both_provider_and_key():
    assert _config(llm_provider="anthropic").llm_enabled is False
    assert _config(llm_api_key="sk-test").llm_enabled is False
    assert _config(llm_provider="anthropic", llm_api_key="sk-test").llm_enabled is True


def test_repr_redacts_secret_fields():
    text = repr(_config(llm_provider="anthropic", llm_api_key="sk-should-not-leak"))
    assert "sk-should-not-leak" not in text
    assert "mqtt-secret" not in text
    assert "supabase-secret" not in text
    assert "operator-secret" not in text


def test_egress_allowlist_parses_comma_separated_hosts(monkeypatch):
    monkeypatch.setenv("TEAM_CODE", "VAMOS")
    monkeypatch.setenv("LLM_EGRESS_ALLOWLIST", "api.anthropic.com, api.openai.com")
    config = Config.from_env()
    assert config.llm_egress_allowlist == ("api.anthropic.com", "api.openai.com")
