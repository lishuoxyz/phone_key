// bdb-PKE alarm protocol (client side).
//
// Pure functions + a small state machine, no BLE code here: the same module is
// used by the PWA, by the hybrid app's WebView and by the test adapter
// (tests/adapters/js/run.mjs). Behaviour is defined by the Python reference in
// tests/reference/protocol_ref.py and the decision table in tests/dt.

import { aes128DecryptBlock, aes128EncryptBlock } from "./aes.js";

export const PIN_DEFAULT = 123789;

export const COMMANDS = {
  lock:   { press: "A50102", release: "A50112" },
  unlock: { press: "A50101", release: "A50111" },
  horn:   { press: "A50104", release: "A50114" },
  mute:   { press: "A50103", release: "A50113" },
  start:  { press: "A50106", release: "A50116" },
  status: { press: "A600",   release: null },
};

export const RULES = {
  releaseDelayMs: 150,
  queryDelayMs: 600,
  armWindowMs: 5000,
  // "status" is already a query; "start" must not be followed by one because
  // it would clear the device's "waiting for the second press" state.
  noQueryAfter: new Set(["start", "status"]),
};

const APP_PREFIX = new TextEncoder().encode("Lenzeapp");
const DEV_PREFIX = new TextEncoder().encode("Lenzedev");

export function hexToBytes(hex) {
  const clean = String(hex).replace(/[^0-9a-fA-F]/g, "");
  if (clean.length % 2 !== 0) throw new Error("odd hex string");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(clean.substr(i * 2, 2), 16);
  return out;
}

export function bytesToHex(bytes) {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").toUpperCase();
}

/** "Lenzeapp"/"Lenzedev" + 4-byte big-endian PIN + 4 zero bytes. */
export function deriveKey(prefix, pin) {
  const key = new Uint8Array(16);
  key.set(prefix, 0);
  key[8] = (pin >>> 24) & 0xff;
  key[9] = (pin >>> 16) & 0xff;
  key[10] = (pin >>> 8) & 0xff;
  key[11] = pin & 0xff;
  return key;
}

export function checksum(cmd) {
  let sum = 0;
  if (cmd.length > 2) for (let i = 2; i < cmd.length; i++) sum += cmd[i];
  return sum & 0xff;
}

export function buildPlain(cmd) {
  if (cmd.length < 1 || cmd.length > 15) throw new Error("command must be 1..15 bytes");
  const plain = new Uint8Array(16);
  plain.set(cmd, 0);
  plain[cmd.length] = checksum(cmd);
  return plain;
}

export function encodeCommand(cmdOrHex, pin = PIN_DEFAULT) {
  const cmd = typeof cmdOrHex === "string" ? hexToBytes(cmdOrHex) : cmdOrHex;
  return aes128EncryptBlock(buildPlain(cmd), deriveKey(APP_PREFIX, pin));
}

export function decodeNotify(cipher, pin = PIN_DEFAULT) {
  if (!cipher || cipher.length !== 16) return null;
  const plain = aes128DecryptBlock(cipher, deriveKey(DEV_PREFIX, pin));
  const plainHex = bytesToHex(plain);
  const op = plain[0];
  if (op === 0xa6) {
    return {
      kind: "status",
      lock: plain[2],
      mode: plain[3],
      pke: plain[5],
      pass1: plain[8],
      pass2: Math.max(0, plain[9] - 1),
      plain: plainHex,
    };
  }
  if (op === 0xa5) {
    return { kind: "event", cmd: plain[2], lock: plain[3], plain: plainHex };
  }
  if (op === 0xa9) {
    return { kind: "heartbeat", counter: plain[2], plain: plainHex };
  }
  return { kind: "unknown", op, plain: plainHex };
}

export function isStarted(state) {
  return !!(state.statusValid && state.mode === 2);
}

/**
 * Client-side model, API-compatible with tests/reference/protocol_ref.py Link.
 *
 *   const link = createLink(123789);
 *   link.connect();
 *   link.command("lock", 0);     // -> [{cmd:"A50102", delayBeforeMs:0}, ...]
 *   link.onNotify(cipherBytes);  // updates link.state
 */
export function createLink(pin = PIN_DEFAULT) {
  const state = {
    connected: false,
    lock: 1,
    mode: 1,
    pke: 0,
    pass1: 0,
    pass2: 0,
    statusValid: false,
    armedAtMs: null,
    hint: "",
  };

  function connect() {
    state.connected = true;
    state.armedAtMs = null;
  }

  function disconnect() {
    state.connected = false;
    state.armedAtMs = null;
    state.statusValid = false;
  }

  function command(action, nowMs = 0) {
    if (!state.connected) throw new Error("not connected");
    const entry = COMMANDS[action];
    if (!entry) throw new Error("unknown action: " + action);

    const writes = [{ cmd: entry.press, delayBeforeMs: 0 }];
    if (entry.release) writes.push({ cmd: entry.release, delayBeforeMs: RULES.releaseDelayMs });
    if (!RULES.noQueryAfter.has(action)) {
      writes.push({ cmd: "A600", delayBeforeMs: RULES.queryDelayMs });
    }

    if (action === "start") {
      if (isStarted(state)) {
        state.hint = "already running";
      } else if (state.armedAtMs !== null && nowMs - state.armedAtMs <= RULES.armWindowMs) {
        state.hint = "starting";
        state.armedAtMs = null;
      } else {
        state.hint = "press again to start";
        state.armedAtMs = nowMs;
      }
    }
    return writes;
  }

  function onNotify(cipher) {
    const parsed = decodeNotify(cipher, pin);
    if (!parsed) return null;
    if (parsed.kind === "status") {
      state.lock = parsed.lock;
      state.mode = parsed.mode;
      state.pke = parsed.pke;
      state.pass1 = parsed.pass1;
      state.pass2 = parsed.pass2;
      state.statusValid = true;
    } else if (parsed.kind === "event") {
      state.lock = parsed.lock;
    }
    return parsed;
  }

  return {
    pin,
    state,
    connect,
    disconnect,
    command,
    onNotify,
    get started() { return isStarted(state); },
  };
}
