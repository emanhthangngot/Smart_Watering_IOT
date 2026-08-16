# MQTT telemetry viewer

`mqtt-read.mjs` is a read-only command-line subscriber for the hackathon telemetry broker. It connects with MQTT 3.1.1 inside a secure WebSocket (WSS) on port 443, subscribes at QoS 0, and prints JSON payloads as they arrive.

## Run

```bash
cd /home/kiet/code/SEAL-Hackathon/vamos_su2026

export MQTT_HOST='mqtt-hackathon.lexatek.vn'
export MQTT_PORT='443'
export MQTT_USERNAME='YOUR_USERNAME'
export MQTT_PASSWORD='YOUR_PASSWORD'
export MQTT_CLIENT_ID='YOUR_TEST_KEY_OR_CLIENT_ID'
export MQTT_TOPIC='hackathon/your-team-code/test/telemetry'
export MQTT_TIMEOUT_MS='30000'
export MQTT_MAX_MESSAGES='1'

node scripts/mqtt-read.mjs
```

For the judge stream, change only `MQTT_TOPIC` to `hackathon/your-team-code/judge/telemetry`.

Do not add credentials to source code or commit them. The hostname `mqtt-hackthon.lexatek.vn` does **not** resolve; use `mqtt-hackathon.lexatek.vn` (with `a`) instead.
