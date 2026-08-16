"""Runtime configuration, loaded from environment variables.

Design reference: plans/reports/plan.md §3.1 ("environment"/"teamCode" must
stay in config, never hard-coded — the team code can change at competition time).

Ownership: dev. Do not edit outside this file to introduce config; add new
keys here and document them in .env.example under the right owner block.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


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
    mqtt_password: str = field(repr=False)
    mqtt_client_id: str
    mqtt_topic: str
    supabase_url: str
    supabase_service_role_key: str = field(repr=False)
    operator_token: str = field(repr=False)
    # --- coordination gate C5: LLM provider + security contract ---
    # Empty llm_provider/llm_api_key means the LLM boundary is disabled —
    # agents/planner.py's narrator is optional and always falls back to a
    # deterministic result, so an unset LLM config is a safe default, not a
    # missing-config error. Never log llm_api_key (repr=False below); never
    # send a request outside llm_egress_allowlist.
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: str = field(default="", repr=False)
    llm_timeout_seconds: float = 8.0
    llm_max_output_tokens: int = 512
    llm_egress_allowlist: tuple[str, ...] = ()
    # Bounded buffering keeps the live worker safe on the small demo server.
    mqtt_queue_max: int = 128
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )

    @property
    def mqtt_enabled(self) -> bool:
        """MQTT is optional; database-backed reads still work without it."""
        return bool(
            self.mqtt_host
            and self.mqtt_username
            and self.mqtt_password
            and self.mqtt_client_id
            and self.mqtt_topic
        )

    @property
    def llm_enabled(self) -> bool:
        """Fail-closed: the LLM boundary is usable only with both a
        provider name and a credential; anything else must fall back."""
        return bool(self.llm_provider and self.llm_api_key)

    @classmethod
    def from_env(cls) -> Config:
        allowlist_raw = _env("LLM_EGRESS_ALLOWLIST", "")
        cors_raw = _env(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:5173,http://127.0.0.1:5173",
        )
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
            llm_provider=_env("LLM_PROVIDER", ""),
            llm_model=_env("LLM_MODEL", ""),
            llm_api_key=_env("LLM_API_KEY", ""),
            llm_timeout_seconds=float(_env("LLM_TIMEOUT_SECONDS", "8.0")),
            llm_max_output_tokens=int(_env("LLM_MAX_OUTPUT_TOKENS", "512")),
            llm_egress_allowlist=tuple(
                host.strip() for host in allowlist_raw.split(",") if host.strip()
            ),
            mqtt_queue_max=max(1, int(_env("MQTT_QUEUE_MAX", "128"))),
            cors_origins=tuple(origin.strip() for origin in cors_raw.split(",") if origin.strip()),
        )
