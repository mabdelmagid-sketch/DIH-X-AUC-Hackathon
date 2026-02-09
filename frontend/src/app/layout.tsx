import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";

export const metadata: Metadata = {
  title: "FlowCast - AI Inventory Intelligence",
  description: "AI-Powered Inventory Intelligence Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
        <ChatPanel />
      </body>
    </html>
  );
}
