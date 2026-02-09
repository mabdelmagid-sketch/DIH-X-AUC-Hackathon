"use client";

import { Sidebar } from "./sidebar";
import { ChatPanel } from "@/components/dashboard/chat-panel";

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-[var(--background)] p-6 lg:p-8">
        {children}
      </main>
      <ChatPanel />
    </div>
  );
}
