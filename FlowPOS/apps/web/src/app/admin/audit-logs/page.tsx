"use client";

import { useTranslations } from "next-intl";
import { AdminLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const ACTION_STYLES: Record<string, string> = {
  create:
    "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  update:
    "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  delete: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  approve:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  reject:
    "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  suspend:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  activate:
    "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400",
  impersonate:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

function getActionStyle(action: string): string {
  const key = action.toLowerCase();
  for (const [keyword, style] of Object.entries(ACTION_STYLES)) {
    if (key.includes(keyword)) return style;
  }
  return "bg-[var(--secondary)] text-[var(--muted-foreground)]";
}

function formatDetails(details: unknown): string {
  if (!details) return "—";
  if (typeof details === "string") return details;
  try {
    const obj = details as Record<string, unknown>;
    return Object.entries(obj)
      .map(([k, v]) => `${k}: ${v}`)
      .join(", ");
  } catch {
    return "—";
  }
}

export default function AuditLogsPage() {
  const t = useTranslations("admin");
  const tc = useTranslations("common");
  const { data, isLoading } = trpc.platformAdmin.auditLogs.list.useQuery({
    limit: 50,
  });

  const logs = data?.logs ?? [];

  return (
    <AdminLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("auditLogs")}
          description={`${data?.total ?? 0} ${t("recordedEvents")}`}
        />

        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">
                {t("loadingLogs")}
              </span>
            </div>
          </div>
        ) : logs.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="history" size={40} />
              <span className="font-body text-sm">{t("noLogs")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("action")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("admin_col")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("target")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("details")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("ip")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("timestamp")}</th>
                </tr>
              </thead>
              <tbody>
                {logs.map(
                  (
                    log: {
                      id: string;
                      action?: string;
                      admin?: { id: string; name?: string; email?: string } | null;
                      target_type?: string;
                      target_id?: string;
                      details?: unknown;
                      ip_address?: string;
                      created_at?: string;
                    },
                    idx: number
                  ) => (
                    <tr
                      key={log.id}
                      className={cn(
                        "bg-[var(--card)] transition-colors hover:bg-[var(--accent)]",
                        idx < logs.length - 1 &&
                          "border-b border-[var(--border)]"
                      )}
                    >
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                            getActionStyle(log.action ?? "")
                          )}
                        >
                          {log.action ?? "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-body text-sm text-[var(--foreground)]">
                        {log.admin?.name ?? log.admin?.email ?? "—"}
                      </td>
                      <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                        {log.target_type
                          ? `${log.target_type}`
                          : "—"}
                      </td>
                      <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)] max-w-[300px] truncate">
                        {formatDetails(log.details)}
                      </td>
                      <td className="px-4 py-3 font-body text-xs text-[var(--muted-foreground)]">
                        {log.ip_address ?? "—"}
                      </td>
                      <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)] whitespace-nowrap">
                        {log.created_at
                          ? new Date(log.created_at).toLocaleString("en-US", {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                              hour12: true,
                            })
                          : "—"}
                      </td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AdminLayout>
  );
}
