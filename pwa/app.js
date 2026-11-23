import {
  createLink,
  encodeCommand,
  hexToBytes,
  bytesToHex,
  PIN_DEFAULT,
} from "./src/protocol.js";
import { AlarmBle, webBluetoothAvailable } from "./src/ble.js";

const $ = (id) => document.getElementById(id);
const link = createLink(PIN_DEFAULT);

const els = {
  status: $("status"),
  version: $("version"),
  device: $("device"),
  lock: $("lock"),
  mode: $("mode"),
  pass: $("pass"),
  hint: $("hint"),
  log: $("log"),
  connect: $("connect"),
  disconnect: $("disconnect"),
  scanNote: $("scanNote"),
};

const ble = new AlarmBle({
  onNotify: (bytes) => {
    const parsed = link.onNotify(bytes);
    if (!parsed) {
      log("← 无法解析的通知 len=" + bytes.length + " " + bytesToHex(bytes));
      return;
    }
    if (parsed.kind === "status") {
      log(`← 状态：${parsed.lock === 2 ? "已上锁" : "已解锁"} · ${parsed.mode === 2 ? "已启动" : "未启动"} · 密码位 ${parsed.pass1}/${parsed.pass2}`);
    } else if (parsed.kind === "event") {
      log("← 按键事件 0x" + parsed.cmd.toString(16).padStart(2, "0"));
    } else if (parsed.kind === "heartbeat") {
      log("← 心跳 " + parsed.counter);
    }
    render();
  },
  onDisconnect: () => {
    link.disconnect();
    log("连接已断开");
    render();
  },
  onLog: log,
});

function log(msg) {
  const line = new Date().toLocaleTimeString() + "  " + msg;
  const text = (els.log.textContent ? els.log.textContent + "\n" : "") + line;
  els.log.textContent = text.split("\n").slice(-80).join("\n");
  els.log.scrollTop = els.log.scrollHeight;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function render() {
  const connected = ble.connected;
  const started = link.started;
  els.status.textContent = connected ? (started ? "已启动" : "已连接") : "未连接";
  els.status.className = "pill " + (connected ? (started ? "started" : "on") : "off");
  els.device.textContent = connected
    ? ble.deviceName + (ble.deviceId ? " · " + ble.deviceId.slice(0, 8) : "")
    : "—";
  els.lock.textContent = link.state.statusValid
    ? link.state.lock === 2 ? "已上锁" : "已解锁"
    : "未知";
  els.mode.textContent = link.state.statusValid
    ? link.state.mode === 2 ? "已启动" : "未启动"
    : "未知";
  els.pass.textContent = link.state.statusValid
    ? link.state.pass1 + " / " + link.state.pass2
    : "—";

  document.querySelectorAll("[data-action]").forEach((btn) => {
    btn.disabled = !connected;
  });
  $("disconnect").disabled = !connected;
  $("keyStart").classList.toggle("running", started);
  $("hint").textContent = hintText();
}

function hintText() {
  if (!ble.connected) return "先扫描并连接报警器（首次需要系统配对，PIN 123789）";
  const h = link.state.hint;
  if (h === "press again to start") return "已按下一次（短响），5 秒内再按一次「启动」";
  if (h === "starting") return "已发送第二次按键，等待车辆确认启动…";
  if (h === "already running") return "车辆已启动；熄火请点「解锁」";
  if (link.started) return "车辆已启动；熄火请点「解锁」";
  return "一键启动：连按两次「启动」；熄火：点一次「解锁」";
}

async function sendAction(action) {
  if (!ble.connected) {
    log("未连接");
    return;
  }
  let writes;
  try {
    writes = link.command(action, Date.now());
  } catch (err) {
    log("发送失败: " + err.message);
    return;
  }
  try {
    for (const w of writes) {
      if (w.delayBeforeMs) await sleep(w.delayBeforeMs);
      await ble.write(encodeCommand(w.cmd, link.pin));
    }
    log("→ " + action + ": " + writes.map((w) => w.cmd).join(" "));
  } catch (err) {
    log("写入失败: " + err.message);
  }
  render();
  /* The start command must not be followed by an A6 query: the device would
   * forget that it is waiting for the second press. */
}

els.connect.addEventListener("click", async () => {
  if (ble.connected) {
    log("已经连接；如需重新扫描，请先点「断开」");
    return;
  }
  try {
    const device = await ble.pickDevice();
    await ble.connect(device);
    link.connect();
    render();
    if (ble.writeCharacteristicUuid && !ble.writeCharacteristicUuid.includes("ffe2")) {
      log("警告：写特征不是 0xffe2，设备可能不响应控制命令");
    }
    await sendAction("status");
  } catch (err) {
    log("连接失败: " + (err && err.message ? err.message : err));
  }
});

els.disconnect.addEventListener("click", () => {
  ble.disconnect();
  link.disconnect();
  render();
});

document.querySelectorAll("[data-action]").forEach((btn) => {
  btn.addEventListener("click", () => sendAction(btn.dataset.action));
});

/* Keep the state fresh while the page is visible; the device also sends a
 * status frame after every action, this is only a safety net. Writes are
 * serialised by the BLE layer, and we never queue a second poll. */
let statusInFlight = false;
setInterval(() => {
  if (document.visibilityState !== "visible" || !ble.connected) return;
  if (statusInFlight) return;
  statusInFlight = true;
  sendAction("status").finally(() => { statusInFlight = false; });
}, 6000);

async function loadVersion() {
  try {
    const res = await fetch("version.json?" + Date.now(), { cache: "no-store" });
    const data = await res.json();
    if (data && data.version) {
      els.version.textContent = "v" + data.version;
      return data.version;
    }
  } catch (err) {
    // offline or served without version.json: keep the placeholder
  }
  els.version.textContent = "v?";
  return "";
}

if (!webBluetoothAvailable()) {
  els.scanNote.hidden = false;
  els.connect.disabled = true;
}

render();
loadVersion().then((version) => {
  log("页面已加载" + (version ? " v" + version : "") + "，等待连接");
});
