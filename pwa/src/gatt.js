// Pure GATT selection helpers (no Web Bluetooth objects here, so the rules can
// be unit-tested in Node with plain mocks).
//
// The real alarm exposes two services:
//   0xffe0   -> 0xffe1 (read+notify), 0xffe2 (write)     <- control channel
//   5833ff01 -> 5833ff02 (write),       5833ff03 (notify)  <- vendor channel
//
// The control channel is 0xffe2. Preferring 5833ff02 by accident makes every
// command silently do nothing (the real device ignores that characteristic).

export const SERVICE_CONTROL = "0000ffe0-0000-1000-8000-00805f9b34fb";
export const SERVICE_VENDOR = "5833ff01-9b8b-5191-6142-22a4536ef123";

export const CHAR_CONTROL_WRITE = "0000ffe2-0000-1000-8000-00805f9b34fb";
export const CHAR_VENDOR_WRITE = "5833ff02-9b8b-5191-6142-22a4536ef123";
export const CHAR_CONTROL_NOTIFY = "0000ffe1-0000-1000-8000-00805f9b34fb";
export const CHAR_VENDOR_NOTIFY = "5833ff03-9b8b-5191-6142-22a4536ef123";

const WRITE_PREFERENCE = [CHAR_CONTROL_WRITE, CHAR_VENDOR_WRITE];
const NOTIFY_UUIDS = [CHAR_CONTROL_NOTIFY, CHAR_VENDOR_NOTIFY];

/** Normalise a BluetoothUUID (string or object) to a lowercase 128-bit string. */
export function normalizeUuid(uuid) {
  if (uuid === null || uuid === undefined) return "";
  let text = String(uuid).trim().toLowerCase();
  if (text.startsWith("0x")) text = text.slice(2);
  if (text.length === 4) return "0000" + text + "-0000-1000-8000-00805f9b34fb";
  return text;
}

function props(ch) {
  return (ch && ch.properties) || {};
}

export function isWritable(ch) {
  const p = props(ch);
  return !!(p.write || p.writeWithoutResponse);
}

export function isNotifiable(ch) {
  const p = props(ch);
  return !!(p.notify || p.indicate);
}

/**
 * Choose the write characteristic. Preference order matters: 0xffe2 first,
 * then 5833ff02, then any other writable characteristic.
 */
export function pickWriteChar(chars) {
  const list = Array.from(chars || []);
  for (const want of WRITE_PREFERENCE) {
    const hit = list.find((ch) => normalizeUuid(ch.uuid) === want && isWritable(ch));
    if (hit) return hit;
  }
  return list.find(isWritable) || null;
}

/** All notification characteristics we know about (0xffe1 and 5833ff03). */
export function pickNotifyChars(chars) {
  const list = Array.from(chars || []);
  const out = [];
  for (const want of NOTIFY_UUIDS) {
    const hit = list.find((ch) => normalizeUuid(ch.uuid) === want && isNotifiable(ch));
    if (hit && !out.includes(hit)) out.push(hit);
  }
  return out;
}

/**
 * Minimal serial queue: Web Bluetooth allows one GATT procedure at a time, so
 * every write must wait for the previous one to settle. Returns a function that
 * enqueues a job and resolves with that job's result.
 */
export function createSerialQueue() {
  let tail = Promise.resolve();
  return function enqueue(job) {
    const run = tail.then(() => job());
    // Keep the chain alive even when a job fails; the caller still sees the
    // rejection through the returned promise.
    tail = run.catch(() => {});
    return run;
  };
}
