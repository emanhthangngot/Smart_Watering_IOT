"""MQTT WSS subscriber, config-driven, feeding ingest/normalize.py.

Design reference: plans/reports/plan.md §3.1-3.2,
plans/260816-0957-data-plane/phase-04-mqtt-client.md. Uses `paho-mqtt` with
websocket transport rather than hand-rolling the WSS+MQTT frame parser —
`scripts/mqtt-read.mjs` is a protocol reference only, not a runtime
dependency.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

import paho.mqtt.client as mqtt

from config import Config

logger = logging.getLogger(__name__)

QOS = 0

# Exponential backoff for reconnects, seconds.
_RECONNECT_MIN_DELAY_S = 1
_RECONNECT_MAX_DELAY_S = 60

BatchHandler = Callable[[dict], None]
StatusHandler = Callable[[str], None]


class MqttClient:
    """Subscribes to config.mqtt_topic and forwards each JSON payload to
    `on_batch`. Reconnects with backoff on drop; never crashes the process.
    """

    def __init__(
        self,
        config: Config,
        on_batch: BatchHandler,
        on_status: StatusHandler | None = None,
    ) -> None:
        self._config = config
        self._on_batch = on_batch
        self._on_status = on_status or (lambda status: None)
        self._client = mqtt.Client(
            client_id=config.mqtt_client_id,
            transport="websockets",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self._client.username_pw_set(config.mqtt_username, config.mqtt_password)
        self._client.tls_set()
        self._client.ws_set_options(path="/")
        self._client.reconnect_delay_set(
            min_delay=_RECONNECT_MIN_DELAY_S, max_delay=_RECONNECT_MAX_DELAY_S
        )
        self._client.on_connect = self._handle_connect
        self._client.on_disconnect = self._handle_disconnect
        self._client.on_message = self._handle_message

    def _handle_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code != 0:
            logger.warning("mqtt: connect failed, reason_code=%s", reason_code)
            self._on_status("CONNECT_FAILED")
            return
        logger.info("mqtt: connected, subscribing to %s", self._config.mqtt_topic)
        self._on_status("CONNECTED")
        client.subscribe(self._config.mqtt_topic, qos=QOS)

    def _handle_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties=None
    ) -> None:
        if reason_code == 0:
            logger.info("mqtt: disconnected normally")
        else:
            logger.warning(
                "mqtt: disconnected (reason_code=%s), reconnecting with backoff", reason_code
            )
        self._on_status("DISCONNECTED")

    def _handle_message(self, client, userdata, message) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("mqtt: dropped non-JSON payload on %s: %s", message.topic, exc)
            return

        try:
            self._on_batch(payload)
        except Exception:
            # A handler failure must never take the MQTT loop down —
            # normalize.py already never raises, but this is the last
            # line of defense so a reconnect storm can't cascade into a crash.
            logger.exception("mqtt: on_batch handler raised, batch dropped")

    def run_forever(self) -> None:
        """Blocking call: connect, subscribe, and process messages until
        interrupted. Reconnects on drop via paho's built-in loop."""
        self._client.connect(self._config.mqtt_host, self._config.mqtt_port)
        self._client.loop_forever(retry_first_connection=True)

    def stop(self) -> None:
        self._client.disconnect()
