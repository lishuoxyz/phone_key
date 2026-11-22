// JSON-lines adapter for the PWA / hybrid JS protocol implementation.
//
//   node tests/adapters/js/run.mjs
//
// It imports ../../../pwa/src/protocol.js, which must export:
//
//   export function createLink(pin) -> {
//     state,                 // see tests/adapters/README.md
//     connect(), disconnect(),
//     command(action, nowMs) -> [{cmd, delayBeforeMs}],
//     onNotify(cipherBytes)  -> parsed | null,
//   }
//
// The adapter itself contains no protocol logic: it only marshals state.

import { createInterface } from "node:readline";

let createLink = null;
let encodeCommand = null;
let decodeNotify = null;
let checksum = null;
let bytesToHex = null;
try {
  const mod = await import("../../../pwa/src/protocol.js");
  createLink = mod.createLink;
  encodeCommand = mod.encodeCommand;
  decodeNotify = mod.decodeNotify;
  checksum = mod.checksum;
  bytesToHex = mod.bytesToHex;
} catch (err) {
  console.error("pwa/src/protocol.js not available yet:", err.message);
  process.exit(3);
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
let link = createLink(123789);

function stateOut() {
  const s = link.state;
  return {
    connected: !!s.connected,
    lock: s.lock ?? 1,
    mode: s.mode ?? 1,
    pke: s.pke ?? 0,
    pass1: s.pass1 ?? 0,
    pass2: s.pass2 ?? 0,
    statusValid: !!s.statusValid,
    armedAtMs: s.armedAtMs ?? null,
    hint: s.hint ?? "",
  };
}

function applyState(state, pin) {
  link = createLink(pin ?? 123789);
  if (!link.state) link.state = {};
  for (const key of ["connected", "lock", "mode", "pke", "pass1", "pass2",
                     "statusValid", "armedAtMs", "hint"]) {
    if (state && state[key] !== undefined) link.state[key] = state[key];
  }
}

function hexToBytes(hex) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}

rl.on("line", (line) => {
  let reply;
  try {
    const req = JSON.parse(line);
    if (req.op === "close") {
      process.exit(0);
    }
    applyState(req.state, req.pin);
    if (req.op === "connect") {
      link.connect();
      reply = { ok: true, state: stateOut() };
    } else if (req.op === "disconnect") {
      link.disconnect();
      reply = { ok: true, state: stateOut() };
    } else if (req.op === "command") {
      const writes = link.command(req.action, req.nowMs ?? 0);
      reply = { ok: true, writes, state: stateOut() };
    } else if (req.op === "notify") {
      const parsed = link.onNotify(hexToBytes(req.cipher));
      reply = { ok: true, parsed: parsed ?? null, state: stateOut() };
    } else if (req.op === "encode") {
      reply = { ok: true, hex: bytesToHex(encodeCommand(req.cmd, req.pin ?? 123789)) };
    } else if (req.op === "checksum") {
      reply = { ok: true, value: checksum(hexToBytes(req.cmd)) };
    } else if (req.op === "decode") {
      reply = { ok: true, parsed: decodeNotify(hexToBytes(req.cipher), req.pin ?? 123789) };
    } else {
      reply = { ok: false, error: "unknown op " + req.op };
    }
  } catch (err) {
    reply = { ok: false, error: String(err && err.message ? err.message : err) };
  }
  process.stdout.write(JSON.stringify(reply) + "\n");
});
