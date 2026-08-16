"""Runtime configuration, loaded from environment variables.

Design reference: plans/reports/plan.md §3.1 ("environment"/"teamCode" must
stay in config, never hard-coded — the team code can change at competition time).

Ownership: dev. Do not edit outside this file to introduce config; add new
keys here and document them in .env.example under the right owner block.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    team_code: str
    environment: str
    actuation_target: str  # "none" | "sim" — §9.2
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    mqtt_client_id: str
    mqtt_topic: str
    supabase_url: str
    supabase_service_role_key: str
    operator_token: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            team_code=_env("TEAM_CODE", "VAMOS"),
            environment=_env("FARM_ENVIRONMENT", "FARM"),
            actuation_target=_env("ACTUATION_TARGET", "none"),
            mqtt_host=_env("MQTT_HOST", "mqtt-hackathon.lexatek.vn"),
            mqtt_port=int(_env("MQTT_PORT", "443")),
            mqtt_username=_env("MQTT_USERNAME", ""),
            mqtt_password=_env("MQTT_PASSWORD", ""),
            mqtt_client_id=_env("MQTT_CLIENT_ID", ""),
            mqtt_topic=_env("MQTT_TOPIC", ""),
            supabase_url=_env("SUPABASE_URL", ""),
            supabase_service_role_key=_env("SUPABASE_SERVICE_ROLE_KEY", ""),
            operator_token=_env("OPERATOR_TOKEN", ""),
        )
