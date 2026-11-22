# 硬件端到端测试（手机 ↔ 报警器模拟器）

自动化覆盖协议逻辑（编解码、时序、状态机），但"手机真的能连上、真的能按键"
只能在真机上验收。用 `code/alarm_sim`（`bdb-PKE-SIM`，PIN `123789`）代替真车，
不会吵到人。

## 准备

1. 报警器模拟器上电（COM6，`192.168.3.65`），网页 `http://192.168.3.65/`
   可以看到锁状态和蜂鸣器日志；
2. **让主板断开**（网页点"断开连接"或关蓝牙）——报警器是单链路，主板占着
   手机就连不上；真机 MAC 已在主板黑名单里，但模拟器没有；
3. 手机安装 Chrome（Android），打开部署好的 HTTPS 页面（PWA）或安装 App；
4. 手机蓝牙打开，靠近模拟器 1–2 米。

## 记录

- 模拟器日志：`http://192.168.3.65/logs` 或 PC 上的
  `logs/devices/ALARM-SIM/…/boot-*.log`；
- 手机侧截图/录屏留档，失败时记录：手机型号、Android 版本、浏览器/App 版本。

## Android 模拟器（MuMu）的限制

MuMu（Android 15）**没有蓝牙适配器**：`dumpsys bluetooth_manager` 里
`address: null`，`svc bluetooth enable` 也保持 OFF。因此模拟器只能验证
页面渲染、HTTPS/Web Bluetooth 提示、按键禁用态；**连接与控车必须真机**。

## 用例

见 [`checklist.md`](checklist.md)，逐项打勾。任何一项失败都算该方案不通过，
必须修复后重跑；三套实现都要各自跑一遍。
