"use client";

import { AdminLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";
import { useTranslations } from "next-intl";

interface StatCard {
  label: string;
  value: string;
  icon: string;
  color: string;
  description: string;
}

export default function SystemPage() {
  const t = useTranslations("admin");
  const tc = useTranslations("common");
  const { data: stats, isLoading } = trpc.platformAdmin.stats.useQuery();

  const cards: StatCard[] = stats
    ? [
        {
          label: t("totalOrgs"),
          value: stats.organizations.total.toLocaleString(),
          icon: "business",
          color: "bg-purple-500",
          description: t("registeredOrgsDesc"),
        },
        {
          label: t("activeOrgs"),
          value: stats.organizations.active.toLocaleString(),
          icon: "verified",
          color: "bg-green-500",
          description: t("activeOrgsDesc"),
        },
        {
          label: t("suspendedOrgs"),
          value: stats.organizations.suspended.toLocaleString(),
          icon: "block",
          color: "bg-red-500",
          description: t("suspendedDesc"),
        },
        {
          label: tc("totalUsers"),
          value: stats.totalUsers.toLocaleString(),
          icon: "group",
          color: "bg-blue-500",
          description: t("allUsers"),
        },
        {
          label: t("pending"),
          value: stats.pendingSignups.toLocaleString(),
          icon: "how_to_reg",
          color: "bg-amber-500",
          description: t("pendingDesc"),
        },
        {
          label: t("ordersWeek"),
          value: stats.recentOrders.toLocaleString(),
          icon: "receipt_long",
          color: "bg-emerald-500",
          description: t("ordersWeekDesc"),
        },
        {
          label: t("partners"),
          value: `${stats.partners.active} / ${stats.partners.total}`,
          icon: "handshake",
          color: "bg-sky-500",
          description: t("partnersDesc"),
        },
      ]
    : [];

  const activePct =
    stats && stats.organizations.total > 0
      ? Math.round(
          (stats.organizations.active / stats.organizations.total) * 100
        )
      : 0;

  return (
    <AdminLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("systemTitle")}
          description={t("systemDescription")}
        />

        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                className="flex h-[140px] animate-pulse rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]"
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {cards.map((card) => (
              <div
                key={card.label}
                className="flex flex-col gap-3 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] px-6 py-5"
              >
                <div className="flex items-center justify-between">
                  <span className="font-body text-[13px] text-[var(--muted-foreground)]">
                    {card.label}
                  </span>
                  <div
                    className={cn(
                      "flex h-9 w-9 items-center justify-center rounded-[var(--radius-m)]",
                      card.color
                    )}
                  >
                    <Icon name={card.icon} size={20} className="text-white" />
                  </div>
                </div>
                <span className="font-brand text-[28px] font-bold text-[var(--foreground)]">
                  {card.value}
                </span>
                <span className="font-body text-xs text-[var(--muted-foreground)]">
                  {card.description}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Activity Rate Bar */}
        {!isLoading && stats && (
          <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] px-6 py-5">
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-1">
                <span className="font-brand text-sm font-semibold text-[var(--foreground)]">
                  {t("orgActivityRate")}
                </span>
                <span className="font-body text-xs text-[var(--muted-foreground)]">
                  {t("ofOrgsActive", { count: stats.organizations.total })}
                </span>
              </div>
              <span className="font-brand text-2xl font-bold text-[var(--primary)]">
                {activePct}%
              </span>
            </div>
            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-[var(--secondary)]">
              <div
                className="h-full rounded-full bg-[var(--primary)] transition-all duration-500"
                style={{ width: `${activePct}%` }}
              />
            </div>
          </div>
        )}

        {/* System Info */}
        {!isLoading && (
          <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="border-b border-[var(--border)] px-6 py-4">
              <span className="font-brand text-sm font-semibold text-[var(--foreground)]">
                {t("systemInfo")}
              </span>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {[
                { label: t("platform"), value: "Flow POS" },
                { label: t("environment"), value: t("production") },
                { label: t("database"), value: t("supabaseDb") },
                { label: t("authProvider"), value: t("supabaseAuth") },
                { label: t("realtime"), value: t("supabaseRealtime") },
              ].map((info) => (
                <div
                  key={info.label}
                  className="flex items-center justify-between px-6 py-3"
                >
                  <span className="font-body text-sm text-[var(--muted-foreground)]">
                    {info.label}
                  </span>
                  <span className="font-body text-sm font-medium text-[var(--foreground)]">
                    {info.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  );
}
