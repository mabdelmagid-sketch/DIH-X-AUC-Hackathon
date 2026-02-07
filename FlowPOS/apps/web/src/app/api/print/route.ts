import { NextRequest, NextResponse } from "next/server";
import * as net from "net";

/**
 * Network print relay — receives ESC/POS data as base64 and sends it
 * to a thermal printer on the local network via raw TCP (port 9100).
 *
 * Browsers can't open raw TCP sockets, so this API route acts as the relay.
 * Works for both PWA and Capacitor deployments as long as the server
 * can reach the printer on the LAN.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { ip, port = 9100, data } = body as {
      ip: string;
      port?: number;
      data: string; // base64 encoded ESC/POS payload
    };

    if (!ip || !data) {
      return NextResponse.json(
        { error: "Missing ip or data" },
        { status: 400 }
      );
    }

    // Validate IP format (basic check — IPv4 or hostname)
    if (!/^[\d.]+$/.test(ip) && !/^[a-zA-Z\d.\-]+$/.test(ip)) {
      return NextResponse.json(
        { error: "Invalid IP address" },
        { status: 400 }
      );
    }

    // Validate port range
    if (port < 1 || port > 65535) {
      return NextResponse.json(
        { error: "Invalid port" },
        { status: 400 }
      );
    }

    // Decode base64 to buffer
    const buffer = Buffer.from(data, "base64");

    // Send to printer via TCP
    await sendToPrinter(ip, port, buffer);

    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

function sendToPrinter(
  ip: string,
  port: number,
  data: Buffer
): Promise<void> {
  return new Promise((resolve, reject) => {
    const socket = new net.Socket();
    const timeout = setTimeout(() => {
      socket.destroy();
      reject(new Error("Connection timed out"));
    }, 5000);

    socket.connect(port, ip, () => {
      socket.write(data, () => {
        clearTimeout(timeout);
        socket.end();
        resolve();
      });
    });

    socket.on("error", (err) => {
      clearTimeout(timeout);
      reject(err);
    });
  });
}
