"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type PrinterType = "browser" | "usb" | "bluetooth" | "network";
export type PaperWidth = "58mm" | "80mm";

/* ─── ESC/POS Commands ─────────────────────────────────── */

const ESC = 0x1b;
const GS = 0x1d;

const CMD = {
  INIT: new Uint8Array([ESC, 0x40]),            // ESC @ — initialize printer
  CUT: new Uint8Array([GS, 0x56, 0x00]),        // GS V 0 — full cut
  FEED3: new Uint8Array([0x0a, 0x0a, 0x0a]),    // 3 line feeds
  ALIGN_CENTER: new Uint8Array([ESC, 0x61, 1]), // ESC a 1 — center
  ALIGN_LEFT: new Uint8Array([ESC, 0x61, 0]),   // ESC a 0 — left
  BOLD_ON: new Uint8Array([ESC, 0x45, 1]),      // ESC E 1
  BOLD_OFF: new Uint8Array([ESC, 0x45, 0]),     // ESC E 0
  DOUBLE_ON: new Uint8Array([GS, 0x21, 0x11]),  // GS ! 0x11 — double width+height
  DOUBLE_OFF: new Uint8Array([GS, 0x21, 0x00]), // GS ! 0x00 — normal
} as const;

/** Strip HTML tags and decode entities → plain text */
function htmlToText(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/div>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<hr[^>]*>/gi, "--------------------------------\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Build ESC/POS binary payload from HTML receipt */
function buildEscPos(html: string): Uint8Array {
  const encoder = new TextEncoder();
  const text = htmlToText(html);
  const parts: Uint8Array[] = [
    CMD.INIT,
    CMD.ALIGN_LEFT,
    encoder.encode(text),
    CMD.FEED3,
    CMD.CUT,
  ];
  const total = parts.reduce((sum, p) => sum + p.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

/* ─── Bluetooth BLE Helpers ────────────────────────────── */

// Common thermal printer BLE service/characteristic UUIDs
const BLE_PRINTER_SERVICES = [
  "000018f0-0000-1000-8000-00805f9b34fb", // Generic printer service
  "e7810a71-73ae-499d-8c15-faa9aef0c3f2", // Common Chinese BLE printers
  "49535343-fe7d-4ae5-8fa9-9fafd205e455", // Microchip BLE (used by many printers)
];

const BLE_WRITE_CHARACTERISTICS = [
  "00002af1-0000-1000-8000-00805f9b34fb", // Generic write
  "bef8d6c9-9c21-4c9e-b632-bd58c1009f9f", // Common Chinese BLE printers
  "49535343-8841-43f4-a8d4-ecbe34729bb3", // Microchip write
];

/** Find a writable characteristic on a BLE GATT server */
async function findWriteCharacteristic(
  server: BluetoothRemoteGATTServer
): Promise<BluetoothRemoteGATTCharacteristic | null> {
  for (const serviceUuid of BLE_PRINTER_SERVICES) {
    try {
      const service = await server.getPrimaryService(serviceUuid);
      for (const charUuid of BLE_WRITE_CHARACTERISTICS) {
        try {
          const char = await service.getCharacteristic(charUuid);
          if (
            char.properties.write ||
            char.properties.writeWithoutResponse
          ) {
            return char;
          }
        } catch {
          // characteristic not found on this service, try next
        }
      }
      // If known UUIDs didn't work, scan all characteristics
      const chars = await service.getCharacteristics();
      for (const char of chars) {
        if (char.properties.write || char.properties.writeWithoutResponse) {
          return char;
        }
      }
    } catch {
      // service not found, try next
    }
  }
  return null;
}

/** Send data over BLE in chunks (BLE has ~20-512 byte MTU) */
async function bleWrite(
  characteristic: BluetoothRemoteGATTCharacteristic,
  data: Uint8Array
) {
  const chunkSize = 100; // safe chunk size for most BLE printers
  for (let i = 0; i < data.length; i += chunkSize) {
    const chunk = data.slice(i, i + chunkSize);
    if (characteristic.properties.writeWithoutResponse) {
      await characteristic.writeValueWithoutResponse(chunk);
    } else {
      await characteristic.writeValueWithResponse(chunk);
    }
    // Small delay between chunks to prevent buffer overflow
    if (i + chunkSize < data.length) {
      await new Promise((r) => setTimeout(r, 20));
    }
  }
}

/* ─── Store Interface ──────────────────────────────────── */

interface PrinterState {
  /* ─── Settings (persisted) ─── */
  printerType: PrinterType;
  paperWidth: PaperWidth;
  autoPrintOnCheckout: boolean;
  autoPrintKitchen: boolean;
  networkPrinterIp: string;
  networkPrinterPort: number;

  /* ─── Runtime ─── */
  isConnected: boolean;
  serialPort: SerialPort | null;
  bluetoothDevice: BluetoothDevice | null;

  /* ─── Actions ─── */
  setPrinterType: (type: PrinterType) => void;
  setPaperWidth: (width: PaperWidth) => void;
  setAutoPrintOnCheckout: (val: boolean) => void;
  setAutoPrintKitchen: (val: boolean) => void;
  setNetworkPrinterIp: (ip: string) => void;
  setNetworkPrinterPort: (port: number) => void;
  connectUsb: () => Promise<boolean>;
  connectBluetooth: () => Promise<boolean>;
  disconnect: () => void;
  printReceipt: (html: string) => Promise<void>;
  printTestPage: () => Promise<void>;
}

/* ─── Store ────────────────────────────────────────────── */

export const usePrinterStore = create<PrinterState>()(
  persist(
    (set, get) => ({
      /* ─── Defaults ─── */
      printerType: "browser",
      paperWidth: "80mm",
      autoPrintOnCheckout: false,
      autoPrintKitchen: false,
      networkPrinterIp: "",
      networkPrinterPort: 9100,

      isConnected: false,
      serialPort: null,
      bluetoothDevice: null,

      /* ─── Setters ─── */
      setPrinterType: (type) => {
        get().disconnect();
        set({ printerType: type });
      },
      setPaperWidth: (width) => set({ paperWidth: width }),
      setAutoPrintOnCheckout: (val) => set({ autoPrintOnCheckout: val }),
      setAutoPrintKitchen: (val) => set({ autoPrintKitchen: val }),
      setNetworkPrinterIp: (ip) => set({ networkPrinterIp: ip }),
      setNetworkPrinterPort: (port) => set({ networkPrinterPort: port }),

      /* ─── USB (Web Serial API — desktop Chrome/Edge) ─── */
      connectUsb: async () => {
        try {
          if (!("serial" in navigator)) {
            throw new Error("Web Serial API not supported in this browser");
          }
          const port = await navigator.serial.requestPort();
          await port.open({ baudRate: 9600 });
          set({ serialPort: port, isConnected: true });
          return true;
        } catch {
          set({ isConnected: false, serialPort: null });
          return false;
        }
      },

      /* ─── Bluetooth (Web Bluetooth API — Android Chrome) ─── */
      connectBluetooth: async () => {
        try {
          if (!("bluetooth" in navigator)) {
            throw new Error(
              "Web Bluetooth not supported. Use Chrome on Android, or install via Capacitor for iOS."
            );
          }
          const device = await navigator.bluetooth.requestDevice({
            acceptAllDevices: true,
            optionalServices: BLE_PRINTER_SERVICES,
          });
          // Connect GATT and verify we can find a writable characteristic
          const server = await device.gatt!.connect();
          const characteristic = await findWriteCharacteristic(server);
          if (!characteristic) {
            server.disconnect();
            throw new Error(
              "Could not find a writable print characteristic on this device"
            );
          }
          set({ bluetoothDevice: device, isConnected: true });
          return true;
        } catch {
          set({ isConnected: false, bluetoothDevice: null });
          return false;
        }
      },

      /* ─── Disconnect ─── */
      disconnect: () => {
        const { serialPort, bluetoothDevice } = get();
        if (serialPort?.readable) {
          serialPort.close().catch(() => {});
        }
        if (bluetoothDevice?.gatt?.connected) {
          bluetoothDevice.gatt.disconnect();
        }
        set({ isConnected: false, serialPort: null, bluetoothDevice: null });
      },

      /* ─── Print Receipt (HTML → printer) ─── */
      printReceipt: async (html: string) => {
        const { printerType, paperWidth } = get();
        const widthPx = paperWidth === "58mm" ? 220 : 302;

        /* ── Browser Print (works everywhere) ── */
        if (printerType === "browser") {
          const printWindow = window.open(
            "",
            "_blank",
            `width=${widthPx + 40},height=600`
          );
          if (!printWindow) return;
          printWindow.document.write(`
            <!DOCTYPE html>
            <html><head>
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { font-family: 'Courier New', monospace; font-size: 12px;
                       width: ${widthPx}px; padding: 8px; margin: 0 auto; }
                @media print {
                  body { width: auto; }
                  @page { margin: 0; size: ${paperWidth === "58mm" ? "58mm" : "80mm"} auto; }
                }
              </style>
            </head><body>${html}</body></html>
          `);
          printWindow.document.close();
          printWindow.focus();
          setTimeout(() => {
            printWindow.print();
            printWindow.close();
          }, 400);
          return;
        }

        /* ── USB Serial (desktop Chrome/Edge) ── */
        if (printerType === "usb") {
          const { serialPort } = get();
          if (!serialPort?.writable) throw new Error("USB printer not connected");
          const payload = buildEscPos(html);
          const writer = serialPort.writable.getWriter();
          try {
            await writer.write(payload);
          } finally {
            writer.releaseLock();
          }
          return;
        }

        /* ── Bluetooth BLE (Android Chrome tablets) ── */
        if (printerType === "bluetooth") {
          const { bluetoothDevice } = get();
          if (!bluetoothDevice?.gatt?.connected) {
            // Try to reconnect
            try {
              await bluetoothDevice?.gatt?.connect();
            } catch {
              throw new Error("Bluetooth printer disconnected. Reconnect in Settings.");
            }
          }
          const server = bluetoothDevice!.gatt!;
          const characteristic = await findWriteCharacteristic(server);
          if (!characteristic) {
            throw new Error("Cannot find printer write characteristic");
          }
          const payload = buildEscPos(html);
          await bleWrite(characteristic, payload);
          return;
        }

        /* ── Network (via API relay) ── */
        if (printerType === "network") {
          const { networkPrinterIp, networkPrinterPort } = get();
          if (!networkPrinterIp) throw new Error("No printer IP configured");
          // Browsers can't open raw TCP sockets, so we relay through our API
          const payload = buildEscPos(html);
          const res = await fetch("/api/print", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              ip: networkPrinterIp,
              port: networkPrinterPort,
              // Send ESC/POS as base64 so it survives JSON
              data: btoa(String.fromCharCode(...payload)),
            }),
          });
          if (!res.ok) {
            const err = await res.text();
            throw new Error(`Network print failed: ${err}`);
          }
          return;
        }
      },

      /* ─── Test Page ─── */
      printTestPage: async () => {
        const now = new Date().toLocaleString();
        const { paperWidth, printerType } = get();
        const testHtml = `
          <div style="text-align:center;margin-bottom:8px">
            <strong style="font-size:16px">Flow POS</strong><br/>
            <span style="font-size:11px">Printer Test</span>
          </div>
          <hr style="border:none;border-top:1px dashed #000;margin:8px 0"/>
          <div style="font-size:11px">
            <div>Status: <strong>Connected</strong></div>
            <div>Time: ${now}</div>
            <div>Paper: ${paperWidth}</div>
            <div>Type: ${printerType}</div>
          </div>
          <hr style="border:none;border-top:1px dashed #000;margin:8px 0"/>
          <div style="text-align:center;font-size:10px;color:#666">
            If you can read this, your printer is working.
          </div>
        `;
        await get().printReceipt(testHtml);
      },
    }),
    {
      name: "flow-pos-printer",
      partialize: (state) => ({
        printerType: state.printerType,
        paperWidth: state.paperWidth,
        autoPrintOnCheckout: state.autoPrintOnCheckout,
        autoPrintKitchen: state.autoPrintKitchen,
        networkPrinterIp: state.networkPrinterIp,
        networkPrinterPort: state.networkPrinterPort,
      }),
    }
  )
);
