# android — 原生 App（方案 B）

状态：待实现。

- 技术：Kotlin + Jetpack Compose，`minSdk 26`、`targetSdk 34`；
- 权限：`BLUETOOTH_SCAN`（neverForLocation）、`BLUETOOTH_CONNECT`、
  `POST_NOTIFICATIONS`；Android 11 及以下另需 `ACCESS_FINE_LOCATION`；
- 结构建议：
  - `ble/`：扫描、连接、GATT（按 UUID 找 `ff02/ffe2`、订阅 `ff03/ffe1`）；
  - `proto/`：AES-128-ECB + 帧编解码（与 `tests/vectors/GoldenVectors.kt` 对拍）；
  - `ui/`：车钥匙盘（2×2 + 中间圆形启动键）；
  - `service/`：前台服务，保持连接 + 自动重连 + 通知。

测试：JVM 单元测试直接引用 `tests/vectors/GoldenVectors.kt` 与
`tests/dt/cases.json`，保证与另外两套实现行为一致。
