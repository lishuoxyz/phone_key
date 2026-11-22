# phone_key 测试

目标：三套实现（`pwa` / `android` / `hybrid`）用**同一份用例**验收，语言不同但
行为必须逐字节一致。

## 测试层次

| 层次 | 文件 | 说明 |
|---|---|---|
| 参考实现 | `reference/protocol_ref.py` | 纯 Python（自带 AES-128），是"什么是正确"的可执行定义 |
| 黄金向量 | `reference/gen_vectors.py` → `vectors/` | 编码/解码/校验的固定答案，含真实抓包明文；生成 JS/Kotlin 绑定 |
| 判定表 | `dt/cases.json` + `dt/run_dt.py` | 条件（连接/动作/是否启动）× 动作（写序列、时序、状态变化） |
| 黑盒适配器 | `adapters/` | 每个实现用 JSON-lines RPC 暴露 `Link`，由同一套判定表驱动 |
| 硬件端到端 | `e2e/` | 手机真机连 `alarm_sim`，按清单人工/半自动验收 |

**为什么不用各语言各写一套测试**：判定表与向量是数据，Python 负责"判卷"，
实现只负责"答题"（适配器）。这样三套实现不可能出现"用例理解不一致"。

## 运行

```bat
cd F:\ESP\code\phone_key\tests
run_all.bat
```

或者：

```bash
python tests/run_all.py
python tests/run_all.py --adapter "node tests/adapters/js/run.mjs"
python tests/run_all.py --adapter "java -cp ... AdapterMain"
```

`run_all.py` 会依次执行：

1. 参考实现自检（AES 标准向量 + 真机密文常量）；
2. 黄金向量漂移检查（`vectors/` 必须与生成器输出一致）；
3. 向量一致性（编码/校验/解码 + AES 往返）；
4. 20 条判定表用例；
5. 可选：对某个实现适配器重跑同一套判定表。

## 判定表覆盖（`dt/cases.json`）

| 组 | 用例 |
|---|---|
| 普通命令 | 上锁、解锁、喇叭、静音（按下 + 150ms 松开 + 600ms 状态查询） |
| 状态查询 | 只发 `A6`，没有按下/松开对 |
| 一键启动 | 第一次（arm）、窗口内第二次、超窗、边界 5000ms、已启动再按 |
| 异常 | 未连接、未知动作 |
| 通知解析 | 已锁/未锁、mode=2 已启动、事件更新锁状态、错误 PIN、8 字节短包 |
| 组合流程 | 启动状态点解锁 → 收到 mode=1 变未启动；断开清 arm、重连重新计数 |
| 字段细节 | pass2 按 (值+1) 存储 |

## 新增实现时怎么做

1. 实现 `protocol.js` / `ProtocolEngine`，导出 `createLink(pin)`（或同等 API）；
2. 按 [`adapters/README.md`](adapters/README.md) 提供适配器；
3. `python tests/run_all.py --adapter "<你的适配器命令>"`，必须全部通过；
4. 真机按 [`e2e/checklist.md`](e2e/checklist.md) 走一遍。

## 注意

- 用例里的 `cmd` 一律是**明文**（`A50102`），加密由实现完成；期望密文在
  `vectors/golden.json` 里单独校验。
- 一键启动必须"连按两次"：一次点击 = `06`+`16` 一对；只发 `06` 设备只短响。
  用例按真机行为编写，改协议时先改 `spec/protocol.json` 和参考实现，再重新
  生成向量，最后同步三套实现。
