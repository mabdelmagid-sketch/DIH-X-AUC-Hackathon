"use client";

import { useTranslations } from "next-intl";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";

interface KDSHeaderProps {
  station?: string;
  statuses: string[];
  activeStatus: string;
  onStatusChange: (status: string) => void;
  soundEnabled?: boolean;
  onToggleSound?: () => void;
  orderCount?: number;
  onBack?: () => void;
}

export function KDSHeader({
  station = "Main",
  statuses,
  activeStatus,
  onStatusChange,
  soundEnabled = true,
  onToggleSound,
  orderCount = 0,
  onBack,
}: KDSHeaderProps) {
  const t = useTranslations("kitchen");
  const tc = useTranslations("common");

  const statusLabel = (s: string): string => {
    const map: Record<string, string> = {
      All: tc("all"),
      New: t("new"),
      "In Progress": t("inProgress"),
      Ready: t("ready"),
    };
    return map[s] ?? s;
  };

  return (
    <header className="flex h-16 items-center justify-between border-b border-[var(--border)] bg-[var(--card)] px-6">
      {/* Left */}
      <div className="flex items-center gap-4">
        {onBack && (
          <button
            onClick={onBack}
            className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-[var(--accent)] transition-colors"
          >
            <Icon name="arrow_back" size={20} className="text-[var(--foreground)]" />
          </button>
        )}
        <span className="font-brand text-lg font-bold text-[var(--foreground)]">
          {t("title")}
        </span>
        <span className="rounded-[var(--radius-pill)] border border-[var(--border)] px-3 py-1 font-body text-xs text-[var(--muted-foreground)]">
          {t("station", { name: station })}
        </span>
        {orderCount > 0 && (
          <span className="rounded-[var(--radius-pill)] bg-[var(--primary)] px-2.5 py-0.5 font-body text-xs font-bold text-white">
            {t("activeCount", { count: orderCount })}
          </span>
        )}
      </div>

      {/* Right */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          {statuses.map((status) => {
            const isActive = status === activeStatus;
            return (
              <button
                key={status}
                onClick={() => onStatusChange(status)}
                className={cn(
                  "rounded-[var(--radius-pill)] px-4 py-1.5 font-body text-sm transition-colors",
                  isActive
                    ? "bg-[var(--primary)] font-medium text-white"
                    : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
                )}
              >
                {statusLabel(status)}
              </button>
            );
          })}
        </div>
        <button
          onClick={onToggleSound}
          className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-pill)] border border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
        >
          <Icon name={soundEnabled ? "volume_up" : "volume_off"} size={20} />
        </button>
      </div>
    </header>
  );
}
