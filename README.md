# phone_key — 手机车钥匙

把 bdb-PKE 报警器的 BLE 控制能力搬到手机上。协议见
[`../spi_lcd_touch/docs/alarm-integration.md`](../spi_lcd_touch/docs/alarm-integration.md)，
方案选型见 [`../spi_lcd_touch/docs/mobile-ble-plan.md`](../spi_lcd_touch/docs/mobile-ble-plan.md)。

## 目录

| 目录 | 方案 | 说明 |
|---|---|---|
| `pwa/` | A. Web Bluetooth（PWA） | 纯前端，Android Chrome 打开即用，需要 HTTPS 托管 |
| `android/` | B. 原生 Android App | Kotlin + BLE，可后台/自动重连/通知 |
| `hybrid/` | C. 原生壳 + WebView + JS Bridge | 复用 PWA 界面，BLE 走原生桥 |
| `tests/` | 测试（先写） | 判定表 + 黑盒/黄金向量，三套实现共用同一份用例 |

## 测试优先

三个方案的语言不同（JS / Kotlin / JS+Java），所以测试不绑定实现语言：

1. **协议规格是唯一真相**：`tests/spec/protocol.json`；
2. **黄金向量**：`tests/vectors/` 由参考实现生成并入库，JS/Kotlin 各有绑定；
3. **判定表用例**：`tests/dt/cases.json`，描述"输入动作 → 应发的字节序列 + 时序 + 状态"；
4. **每个实现提供适配器**：读同一份用例、输出结果，由 `tests/run_all.py` 统一比对；
5. **硬件端到端**（可选）：手机真机连 `alarm_sim`，按 `tests/e2e/` 的手工/半自动清单验收。

先跑测试（此时还没有实现，参考实现会先通过）：

```bat
cd F:\ESP\code\phone_key\tests
run_all.bat
```

当前状态：参考实现 + 黄金向量 + 20 条判定表全部通过，适配器机制已用
"正确适配器必须通过 / 注入 bug 的适配器必须被抓到"自测过。

三套实现完成后，分别执行：

```bat
python tests\run_all.py --adapter "node tests\adapters\js\run.mjs"
python tests\run_all.py --adapter "java -cp android\adapter\build\adapter.jar AdapterMain"
```

## 部署到 GitHub Pages

仓库已带 `.github/workflows/pages.yml`：推送到 `main` 后自动把 `pwa/` 发布为
GitHub Pages 站点（Settings → Pages 的 Source 选 "GitHub Actions"）。

一次性初始化（在 GitHub 上先建一个空仓库，比如 `phone_key`）：

```bat
cd F:\ESP\code\phone_key
git remote add origin https://github.com/<你的用户名>/phone_key.git
git push -u origin main
```

推送后 Actions 跑完，页面地址是：

```
https://<你的用户名>.github.io/phone_key/
```

手机 Chrome 打开即可（HTTPS，满足 Web Bluetooth 的安全上下文要求），
可"添加到主屏幕"当 App 用。
