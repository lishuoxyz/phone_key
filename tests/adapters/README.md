"""Adapter contract for phone_key implementations.

Each implementation (PWA, hybrid, Android) exposes the same ``Link`` behaviour so
that the Python test driver can judge it with exactly the same decision-table
cases. The adapter is a small process that speaks JSON-lines over stdin/stdout.

## Protocol

Request (one JSON object per line):

```json
{"op":"connect","state":{...}}
{"op":"disconnect","state":{...}}
{"op":"command","action":"lock","nowMs":0,"state":{...}}
{"op":"notify","cipher":"<16-byte hex>","state":{...}}
{"op":"encode","cmd":"A50106","pin":123789}
{"op":"checksum","cmd":"A50102"}
{"op":"decode","cipher":"<16-byte hex>","pin":123789}
```

Response:

```json
{"ok":true,"state":{...}}
{"ok":true,"writes":[{"cmd":"A50102","delayBeforeMs":0}],"state":{...}}
{"ok":true,"parsed":{"kind":"status","lock":2,"mode":1},"state":{...}}
{"ok":true,"hex":"3DC21FE3..."}
{"ok":true,"value":2}
```

`state` fields: `connected`, `lock`, `mode`, `pke`, `pass1`, `pass2`,
`statusValid`, `armedAtMs` (null or epoch-ms used only for the 5 s start
window), `hint`.

`cmd` is the **plaintext** command (`A50102`); the implementation encrypts it.
`delayBeforeMs` is relative to the previous write (150 for release, 600 for the
status query).

## Implementations

| 方案 | 适配器 | 说明 |
|---|---|---|
| PWA | [`js/run.mjs`](js/run.mjs) | `import` 自 `pwa/src/protocol.js` |
| hybrid | 复用 `js/run.mjs` | 协议层同 PWA，BLE 走原生桥 |
| Android | `kotlin/`（待补） | JVM CLI，复用 App 的 `proto/` 模块 |

Run the suite against an implementation:

```bat
python tests\run_all.py --adapter "node tests\adapters\js\run.mjs"
```
