// Node unit tests for the pure GATT helpers (no Web Bluetooth needed).
//
//   node --test tests/unit/
//
// These cover the two bugs found on the real device:
//   1. 5833ff02 was chosen instead of 0xffe2 (commands silently ignored);
//   2. overlapping writes ("GATT operation already in progress").

import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeUuid,
  pickWriteChar,
  pickNotifyChars,
  createSerialQueue,
  CHAR_CONTROL_WRITE,
  CHAR_VENDOR_WRITE,
  CHAR_CONTROL_NOTIFY,
  CHAR_VENDOR_NOTIFY,
} from "../../pwa/src/gatt.js";

const write = (uuid) => ({ uuid, properties: { write: true } });
const writeNoRsp = (uuid) => ({ uuid, properties: { writeWithoutResponse: true } });
const notify = (uuid) => ({ uuid, properties: { notify: true } });
const readOnly = (uuid) => ({ uuid, properties: { read: true } });

test("normalizeUuid expands 16-bit short UUIDs", () => {
  assert.equal(normalizeUuid("ffe2"), "0000ffe2-0000-1000-8000-00805f9b34fb");
  assert.equal(normalizeUuid(" 0xFFE1 "), "0000ffe1-0000-1000-8000-00805f9b34fb");
  assert.equal(normalizeUuid(CHAR_VENDOR_WRITE), CHAR_VENDOR_WRITE);
});

test("pickWriteChar prefers 0xffe2 even when ff02 comes first", () => {
  const chars = [write(CHAR_VENDOR_WRITE), write(CHAR_CONTROL_WRITE)];
  assert.equal(pickWriteChar(chars).uuid, CHAR_CONTROL_WRITE);
});

test("pickWriteChar keeps 0xffe2 when the vendor channel is missing", () => {
  assert.equal(pickWriteChar([write(CHAR_CONTROL_WRITE)]).uuid, CHAR_CONTROL_WRITE);
});

test("pickWriteChar falls back to 5833ff02 only when 0xffe2 is absent", () => {
  assert.equal(pickWriteChar([write(CHAR_VENDOR_WRITE)]).uuid, CHAR_VENDOR_WRITE);
});

test("pickWriteChar accepts write-without-response characteristics", () => {
  assert.equal(normalizeUuid(pickWriteChar([writeNoRsp("ffe2")]).uuid), CHAR_CONTROL_WRITE);
});

test("pickWriteChar ignores read-only and returns null when nothing is writable", () => {
  assert.equal(pickWriteChar([readOnly(CHAR_CONTROL_WRITE)]), null);
  assert.equal(pickWriteChar([]), null);
});

test("pickNotifyChars selects both 0xffe1 and 5833ff03", () => {
  const chars = [notify(CHAR_VENDOR_NOTIFY), notify(CHAR_CONTROL_NOTIFY), readOnly("ffe2")];
  const picked = pickNotifyChars(chars).map((c) => c.uuid);
  assert.deepEqual(picked, [CHAR_CONTROL_NOTIFY, CHAR_VENDOR_NOTIFY]);
});

test("pickNotifyChars ignores characteristics without notify/indicate", () => {
  assert.deepEqual(pickNotifyChars([readOnly(CHAR_CONTROL_NOTIFY)]), []);
});

test("serial queue runs jobs in order", async () => {
  const enqueue = createSerialQueue();
  const seen = [];
  const slow = (id, ms) =>
    enqueue(
      () =>
        new Promise((resolve) => {
          setTimeout(() => {
            seen.push(id);
            resolve(id);
          }, ms);
        })
    );
  const p1 = slow("a", 30);
  const p2 = slow("b", 5);
  const p3 = slow("c", 1);
  assert.deepEqual(await Promise.all([p1, p2, p3]), ["a", "b", "c"]);
  assert.deepEqual(seen, ["a", "b", "c"]);
});

test("serial queue survives a failing job", async () => {
  const enqueue = createSerialQueue();
  const order = [];
  await assert.rejects(
    enqueue(async () => {
      order.push("bad");
      throw new Error("boom");
    })
  );
  const result = await enqueue(async () => {
    order.push("good");
    return 42;
  });
  assert.equal(result, 42);
  assert.deepEqual(order, ["bad", "good"]);
});
