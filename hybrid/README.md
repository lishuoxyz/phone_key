# hybrid — 原生壳 + WebView + JS Bridge（方案 C）

状态：待实现。

- 界面复用 `pwa/` 的 HTML/CSS；
- **Android WebView 不支持 Web Bluetooth**，BLE 必须由原生实现，通过
  `@JavascriptInterface` 暴露：
  `scan() / connect(mac) / write(hex) / subscribe()` 和回调 `onNotify(hex)`；
- 适合"界面频繁改、又需要后台可靠"的后期形态；
- 签名与分发同 `android/`（自签名 keystore 即可）。
