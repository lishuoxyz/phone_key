# Kotlin adapter（待实现）

Android App 与 hybrid 的原生 BLE 层实现 `ProtocolEngine`（或在 `proto/` 里），
再提供一个小型 JVM CLI 作为适配器；协议与命令行契约见
[`../README.md`](../README.md)。

建议结构：

```
android/app/src/main/java/.../proto/
  AesEcb.kt           // javax.crypto AES/ECB/NoPadding
  FrameCodec.kt       // checksum + padding + encode/decode
  LinkState.kt        // lock/mode/pke/pass/armed
  ProtocolEngine.kt   // connect/disconnect/command(action, nowMs)/onNotify(bytes)
  AdapterMain.kt      // 读 stdin 的 JSON 行，调用 ProtocolEngine，写 stdout
```

对拍：

```bat
python tests\run_all.py --adapter "java -cp android\adapter\build\adapter.jar AdapterMain"
```

JVM 单元测试可直接引用 [`../../vectors/GoldenVectors.kt`](../../vectors/GoldenVectors.kt)：
- `encode` 表：`PIN` + 明文命令 → 期望密文；
- `decode` 表：密文 → 明文 / 状态字段；
- `dt/cases.json` 里的用例用同一个适配器跑，保证与 PWA 行为一致。
