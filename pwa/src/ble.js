// Web Bluetooth transport for the bdb-PKE alarm.
//
// Only the GATT plumbing lives here; protocol/state logic is in protocol.js.
// Requires a secure context (https:// or localhost) and Chrome/Edge on Android.

export const SERVICE_CONTROL = "0000ffe0-0000-1000-8000-00805f9b34fb";
export const SERVICE_VENDOR = "5833ff01-9b8b-5191-6142-22a4536ef123";
export const CHAR_WRITE = "0000ffe2-0000-1000-8000-00805f9b34fb";
export const CHAR_WRITE_ALT = "5833ff02-9b8b-5191-6142-22a4536ef123";
export const CHAR_NOTIFY = "0000ffe1-0000-1000-8000-00805f9b34fb";
export const CHAR_NOTIFY_ALT = "5833ff03-9b8b-5191-6142-22a4536ef123";

export function webBluetoothAvailable() {
  return typeof navigator !== "undefined" && !!navigator.bluetooth;
}

export class AlarmBle {
  constructor({ onNotify, onDisconnect, onLog } = {}) {
    this.device = null;
    this.server = null;
    this.writeChar = null;
    this.notifyChars = [];
    this.onNotify = onNotify || (() => {});
    this.onDisconnect = onDisconnect || (() => {});
    this.onLog = onLog || (() => {});
    this.deviceName = "";
    this.deviceId = "";
  }

  get connected() {
    return !!(this.device && this.device.gatt && this.device.gatt.connected);
  }

  async pickDevice() {
    if (!webBluetoothAvailable()) {
      throw new Error("此浏览器不支持 Web Bluetooth（需要 Android Chrome 且页面为 HTTPS）");
    }
    const device = await navigator.bluetooth.requestDevice({
      filters: [{ namePrefix: "bdb-PKE" }],
      optionalServices: [SERVICE_CONTROL, SERVICE_VENDOR],
    });
    return device;
  }

  async connect(device) {
    this.device = device;
    this.deviceName = device.name || "(unknown)";
    this.deviceId = device.id || "";
    device.addEventListener("gattserverdisconnected", () => {
      this.server = null;
      this.writeChar = null;
      this.notifyChars = [];
      this.onDisconnect();
    });

    this.onLog("连接 " + this.deviceName + " …");
    this.server = await device.gatt.connect();

    // Write characteristic: prefer 0xffe2, fall back to 5833ff02.
    this.writeChar = await this.findChar(this.server, [CHAR_WRITE, CHAR_WRITE_ALT], "write");
    if (!this.writeChar) throw new Error("找不到可写特征（0xffe2 / 5833ff02）");

    // Notification characteristics: both, when present.
    this.notifyChars = [];
    for (const uuid of [CHAR_NOTIFY, CHAR_NOTIFY_ALT]) {
      try {
        const ch = await this.findChar(this.server, [uuid], "notify");
        if (ch) {
          await ch.startNotifications();
          ch.addEventListener("characteristicvaluechanged", (ev) => {
            const view = ev.target.value;
            const bytes = new Uint8Array(view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength));
            this.onNotify(bytes);
          });
          this.notifyChars.push(ch);
        }
      } catch (err) {
        this.onLog("订阅 " + uuid.slice(4, 8) + " 失败: " + err.message);
      }
    }
    if (!this.notifyChars.length) throw new Error("没有可用的通知特征");
    this.onLog("已连接，写特征 " + shortUuid(this.writeChar.uuid));
    return this;
  }

  async findChar(server, uuids, prop) {
    for (const uuid of uuids) {
      const service = await serviceOf(server, uuid);
      if (!service) continue;
      try {
        const ch = await service.getCharacteristic(uuid);
        const p = ch.properties || {};
        if (prop === "write" && (p.write || p.writeWithoutResponse)) return ch;
        if (prop === "notify" && (p.notify || p.indicate)) return ch;
      } catch (err) {
        // characteristic not in this service: try the next candidate
      }
    }
    // Fall back to walking all services (some firmwares report odd UUID bases).
    try {
      const services = await server.getPrimaryServices();
      for (const service of services) {
        let chars = [];
        try { chars = await service.getCharacteristics(); } catch (err) { continue; }
        for (const ch of chars) {
          const u = String(ch.uuid).toLowerCase();
          if (!uuids.some((want) => u === want.toLowerCase())) continue;
          const p = ch.properties || {};
          if (prop === "write" && (p.write || p.writeWithoutResponse)) return ch;
          if (prop === "notify" && (p.notify || p.indicate)) return ch;
        }
      }
    } catch (err) {
      // ignore
    }
    return null;
  }

  async write(bytes) {
    if (!this.writeChar) throw new Error("未连接");
    if (this.writeChar.properties && this.writeChar.properties.write) {
      await this.writeChar.writeValueWithResponse(bytes);
    } else {
      await this.writeChar.writeValueWithoutResponse(bytes);
    }
  }

  disconnect() {
    if (this.device && this.device.gatt && this.device.gatt.connected) {
      this.device.gatt.disconnect();
    }
    this.server = null;
    this.writeChar = null;
    this.notifyChars = [];
  }
}

async function serviceOf(server, uuid) {
  try {
    return await server.getPrimaryService(uuid);
  } catch (err) {
    return null;
  }
}

function shortUuid(uuid) {
  const s = String(uuid);
  return s.length > 8 ? s.slice(4, 8) : s;
}
