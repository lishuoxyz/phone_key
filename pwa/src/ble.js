// Web Bluetooth transport for the bdb-PKE alarm.
//
// Only the GATT plumbing lives here; protocol/state logic is in protocol.js.
// Requires a secure context (https:// or localhost) and Chrome/Edge on Android.

import {
  SERVICE_CONTROL,
  SERVICE_VENDOR,
  normalizeUuid,
  pickWriteChar,
  pickNotifyChars,
  createSerialQueue,
} from "./gatt.js";

export { SERVICE_CONTROL, SERVICE_VENDOR };

export function webBluetoothAvailable() {
  if (typeof navigator === "undefined" || !navigator.bluetooth) return false;
  // Web Bluetooth is only exposed in a secure context; http://LAN-IP is not.
  return typeof window !== "undefined" && window.isSecureContext !== false;
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
    this.queue = createSerialQueue();
  }

  get connected() {
    return !!(this.device && this.device.gatt && this.device.gatt.connected);
  }

  get writeCharacteristicUuid() {
    return this.writeChar ? normalizeUuid(this.writeChar.uuid) : "";
  }

  async pickDevice() {
    if (!webBluetoothAvailable()) {
      throw new Error("此浏览器不支持 Web Bluetooth（需要 Android Chrome 且页面为 HTTPS）");
    }
    return navigator.bluetooth.requestDevice({
      filters: [{ namePrefix: "bdb-PKE" }],
      optionalServices: [SERVICE_CONTROL, SERVICE_VENDOR],
    });
  }

  async connect(device) {
    if (this.connected && this.device === device) {
      return this;
    }
    if (this.connected) {
      this.disconnect();
    }

    this.device = device;
    this.deviceName = device.name || "(unknown)";
    this.deviceId = device.id || "";
    device.addEventListener("gattserverdisconnected", () => this.handleDisconnected());

    this.onLog("连接 " + this.deviceName + " …");
    this.server = await device.gatt.connect();

    const chars = await this.collectCharacteristics();
    this.writeChar = pickWriteChar(chars);
    if (!this.writeChar) {
      throw new Error("找不到可写特征（期望 0xffe2）");
    }

    this.notifyChars = [];
    for (const ch of pickNotifyChars(chars)) {
      try {
        await ch.startNotifications();
        ch.addEventListener("characteristicvaluechanged", (ev) => {
          const view = ev.target.value;
          const bytes = new Uint8Array(
            view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength)
          );
          this.onNotify(bytes);
        });
        this.notifyChars.push(ch);
      } catch (err) {
        this.onLog("订阅 " + shortUuid(ch.uuid) + " 失败: " + err.message);
      }
    }
    if (!this.notifyChars.length) {
      throw new Error("没有可用的通知特征（0xffe1 / 5833ff03）");
    }

    const notifyNames = this.notifyChars.map((ch) => shortUuid(ch.uuid)).join("+");
    this.onLog(
      "已连接，写特征 " + shortUuid(this.writeChar.uuid) + "，通知 " + notifyNames
    );
    return this;
  }

  /** Read every characteristic of the two known services (fallback: all). */
  async collectCharacteristics() {
    const out = [];
    const services = [];
    for (const uuid of [SERVICE_CONTROL, SERVICE_VENDOR]) {
      try {
        services.push(await this.server.getPrimaryService(uuid));
      } catch (err) {
        // service absent: ignore, the fallback below covers unusual layouts
      }
    }
    if (!services.length) {
      try {
        services.push(...(await this.server.getPrimaryServices()));
      } catch (err) {
        // nothing we can do
      }
    }
    for (const service of services) {
      try {
        out.push(...(await service.getCharacteristics()));
      } catch (err) {
        // ignore a service that refuses enumeration
      }
    }
    return out;
  }

  handleDisconnected() {
    this.server = null;
    this.writeChar = null;
    this.notifyChars = [];
    this.queue = createSerialQueue();
    this.onDisconnect();
  }

  /**
   * Serialised write: Web Bluetooth allows only one GATT procedure at a time,
   * so a status query fired by the timer must not overlap a key press.
   */
  write(bytes) {
    const char = this.writeChar;
    if (!char) {
      return Promise.reject(new Error("未连接"));
    }
    return this.queue(async () => {
      const p = char.properties || {};
      if (p.write) {
        await char.writeValueWithResponse(bytes);
      } else {
        await char.writeValueWithoutResponse(bytes);
      }
    });
  }

  disconnect() {
    if (this.device && this.device.gatt && this.device.gatt.connected) {
      this.device.gatt.disconnect();
    }
    this.handleDisconnected();
  }
}

function shortUuid(uuid) {
  const s = normalizeUuid(uuid);
  return s.length > 8 ? s.slice(4, 8) : s;
}
