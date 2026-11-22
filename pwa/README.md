# pwa — Web Bluetooth（方案 A）

状态：待实现。

- 技术：原生 JS + `navigator.bluetooth`，无构建步骤；
- 部署：**必须 HTTPS**（GitHub Pages / Vercel），`http://192.168.x.x` 下
  `navigator.bluetooth` 不可用；
- 能力：扫描 → 连接 → 系统 PIN 配对 → 上锁/解锁/喇叭/静音 → 连按两次启动 →
  解锁熄火 → 状态显示；
- 协议逻辑放在 `src/protocol.js`（纯函数，可在 Node 里跑单元测试）。

约定（测试适配器依赖）：

```js
// src/protocol.js
export function encodeCommand(cmdBytes, pin) -> Uint8Array(16)
export function decodeNotify(bytes16, pin) -> {kind:"status"|"event"|"heartbeat", ...}
export function buildAction(action, state) -> [{hex, delayMs}]
```
