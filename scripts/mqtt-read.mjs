#!/usr/bin/env node

import crypto from "node:crypto";
import tls from "node:tls";

const required = [
  "MQTT_HOST",
  "MQTT_USERNAME",
  "MQTT_PASSWORD",
  "MQTT_CLIENT_ID",
  "MQTT_TOPIC",
];

const missing = required.filter((name) => !process.env[name]);
if (missing.length > 0) {
  console.error(`Configuration error: missing ${missing.join(", ")}.`);
  process.exitCode = 2;
} else {
  run();
}

function run() {
  const config = {
    host: process.env.MQTT_HOST,
    port: Number(process.env.MQTT_PORT ?? 443),
    username: process.env.MQTT_USERNAME,
    password: process.env.MQTT_PASSWORD,
    clientId: process.env.MQTT_CLIENT_ID,
    topic: process.env.MQTT_TOPIC,
    timeoutMs: Number(process.env.MQTT_TIMEOUT_MS ?? 30_000),
    maxMessages: Number(process.env.MQTT_MAX_MESSAGES ?? 0),
  };

  if (!Number.isInteger(config.port) || config.port < 1 || config.port > 65_535) {
    fail("Configuration error: MQTT_PORT must be between 1 and 65535.", 2);
    return;
  }
  if (!Number.isFinite(config.timeoutMs) || config.timeoutMs < 1) {
    fail("Configuration error: MQTT_TIMEOUT_MS must be a positive number.", 2);
    return;
  }
  if (!Number.isInteger(config.maxMessages) || config.maxMessages < 0) {
    fail("Configuration error: MQTT_MAX_MESSAGES must be a non-negative integer.", 2);
    return;
  }

  console.log("MQTT telemetry viewer (read-only)");
  console.log(`Broker: wss://${config.host}:${config.port}`);
  console.log(`Topic: ${config.topic}`);
  console.log(`Client ID: ${redact(config.clientId)}`);
  console.log("Credentials: configured (not displayed)");

  let socket;
  let receivedMessages = 0;
  let websocketReady = false;
  let mqttReady = false;
  let buffer = Buffer.alloc(0);
  let finished = false;

  const finish = (message, exitCode = 0) => {
    if (finished) return;
    finished = true;
    clearTimeout(timeout);
    if (message) console.log(message);
    process.exitCode = exitCode;
    socket?.end();
  };

  const timeout = setTimeout(() => {
    finish(`Finished: ${receivedMessages} message(s) received before timeout.`);
  }, config.timeoutMs);

  socket = tls.connect({
    host: config.host,
    port: config.port,
    servername: config.host,
    rejectUnauthorized: true,
  });

  socket.on("secureConnect", () => {
    const key = crypto.randomBytes(16).toString("base64");
    socket.write([
      "GET / HTTP/1.1",
      `Host: ${config.host}`,
      "Upgrade: websocket",
      "Connection: Upgrade",
      `Sec-WebSocket-Key: ${key}`,
      "Sec-WebSocket-Version: 13",
      "Sec-WebSocket-Protocol: mqtt",
      "",
      "",
    ].join("\r\n"));
  });

  socket.on("data", (chunk) => {
    buffer = Buffer.concat([buffer, chunk]);

    if (!websocketReady) {
      const headerEnd = buffer.indexOf("\r\n\r\n");
      if (headerEnd === -1) return;
      const statusLine = buffer.subarray(0, headerEnd).toString("utf8").split("\r\n")[0];
      if (!statusLine.includes(" 101 ")) {
        finish(`WebSocket upgrade failed: ${statusLine}`, 1);
        return;
      }
      websocketReady = true;
      buffer = buffer.subarray(headerEnd + 4);
      console.log("WSS connected. Sending MQTT CONNECT...");
      socket.write(websocketFrame(mqttConnectPacket(config)));
    }

    parseWebSocketFrames();
  });

  socket.on("error", (error) => finish(`Transport error: ${error.code ?? error.message}`, 1));
  socket.on("end", () => {
    if (!finished) finish("Broker closed the connection.", mqttReady ? 0 : 1);
  });

  function parseWebSocketFrames() {
    while (buffer.length >= 2) {
      const opcode = buffer[0] & 0x0f;
      let payloadLength = buffer[1] & 0x7f;
      let offset = 2;
      if (payloadLength === 126) {
        if (buffer.length < 4) return;
        payloadLength = buffer.readUInt16BE(2);
        offset = 4;
      } else if (payloadLength === 127) {
        if (buffer.length < 10) return;
        const length = buffer.readBigUInt64BE(2);
        if (length > BigInt(Number.MAX_SAFE_INTEGER)) {
          finish("WebSocket payload is too large.", 1);
          return;
        }
        payloadLength = Number(length);
        offset = 10;
      }
      if (buffer.length < offset + payloadLength) return;
      const payload = buffer.subarray(offset, offset + payloadLength);
      buffer = buffer.subarray(offset + payloadLength);

      if (opcode === 0x8) return finish("Broker closed the WebSocket connection.");
      if (opcode === 0x9) {
        socket.write(websocketFrame(payload, 0xA));
        continue;
      }
      if (opcode === 0x2) handleMqttPacket(payload);
    }
  }

  function handleMqttPacket(packet) {
    const type = packet[0] >> 4;
    const { bodyOffset } = mqttRemainingLength(packet);
    if (type === 2) {
      if (packet.length < bodyOffset + 2) return finish("Invalid MQTT CONNACK.", 1);
      if (packet[bodyOffset + 1] !== 0) return finish(`MQTT authentication refused (CONNACK ${packet[bodyOffset + 1]}).`, 1);
      console.log("MQTT authenticated. Subscribing at QoS 0...");
      socket.write(websocketFrame(mqttSubscribePacket(config.topic)));
      return;
    }
    if (type === 9) {
      if (packet.length < bodyOffset + 3 || packet[bodyOffset + 2] === 0x80) return finish("MQTT subscription refused.", 1);
      mqttReady = true;
      console.log("Subscription acknowledged. Waiting for telemetry...");
      return;
    }
    if (type === 3) {
      const topicLength = packet.readUInt16BE(bodyOffset);
      const messageTopic = packet.subarray(bodyOffset + 2, bodyOffset + 2 + topicLength).toString("utf8");
      const qos = (packet[0] >> 1) & 0x03;
      const payloadOffset = bodyOffset + 2 + topicLength + (qos > 0 ? 2 : 0);
      const body = packet.subarray(payloadOffset).toString("utf8");
      receivedMessages += 1;
      console.log(`\n--- Message ${receivedMessages} · ${messageTopic} ---`);
      try {
        console.log(JSON.stringify(JSON.parse(body), null, 2));
      } catch {
        console.log(`Non-JSON UTF-8 payload:\n${body}`);
      }
      if (config.maxMessages > 0 && receivedMessages >= config.maxMessages) {
        finish(`Finished: reached MQTT_MAX_MESSAGES=${config.maxMessages}.`);
      }
    }
  }
}

function mqttConnectPacket(config) {
  const variableHeader = Buffer.concat([encodeString("MQTT"), Buffer.from([4, 0xc2, 0, 30])]);
  const payload = Buffer.concat([encodeString(config.clientId), encodeString(config.username), encodeString(config.password)]);
  return Buffer.concat([Buffer.from([0x10, variableHeader.length + payload.length]), variableHeader, payload]);
}

function mqttSubscribePacket(topic) {
  const payload = Buffer.concat([encodeString(topic), Buffer.from([0])]);
  return Buffer.concat([Buffer.from([0x82, payload.length + 2, 0, 1]), payload]);
}

function mqttRemainingLength(packet) {
  let multiplier = 1;
  let value = 0;
  let index = 1;
  let encodedByte;
  do {
    if (index >= packet.length || index > 4) throw new Error("Invalid MQTT remaining length.");
    encodedByte = packet[index];
    value += (encodedByte & 0x7f) * multiplier;
    multiplier *= 128;
    index += 1;
  } while ((encodedByte & 0x80) !== 0);
  if (packet.length < index + value) throw new Error("Incomplete MQTT packet.");
  return { bodyOffset: index, value };
}

function encodeString(value) {
  const bytes = Buffer.from(value, "utf8");
  const length = Buffer.alloc(2);
  length.writeUInt16BE(bytes.length);
  return Buffer.concat([length, bytes]);
}

function websocketFrame(payload, opcode = 0x2) {
  const mask = crypto.randomBytes(4);
  let header;
  if (payload.length < 126) header = Buffer.from([0x80 | opcode, 0x80 | payload.length]);
  else if (payload.length < 65_536) header = Buffer.from([0x80 | opcode, 0xfe, payload.length >> 8, payload.length & 0xff]);
  else throw new Error("Outgoing MQTT packet is too large.");
  const maskedPayload = Buffer.from(payload);
  for (let index = 0; index < maskedPayload.length; index += 1) maskedPayload[index] ^= mask[index % 4];
  return Buffer.concat([header, mask, maskedPayload]);
}

function redact(value) {
  return value.length <= 8 ? "[redacted]" : `${value.slice(0, 4)}…${value.slice(-4)}`;
}

function fail(message, code) {
  console.error(message);
  process.exitCode = code;
}
