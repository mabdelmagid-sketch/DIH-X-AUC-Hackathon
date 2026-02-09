"use client";

import { useTranslations } from "next-intl";
import { AdminLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const useMetricIcons = (): Record<string, { icon: string; color: string }> => {
  return {
    totalUsers: { icon: "group", color: "bg-blue-500" },
    totalOrgs: { icon: "business", color: "bg-purple-500" },
    pendingSignups: { icon: "how_to_reg", color: "bg-amber-500" },
    recentOrders: { icon: "receipt_long", color: "bg-emerald-500" },
  };
};

export default function UsersPage() {
  const { data: stats, isLoading } = trpc.platformAdmin.stats.useQuery();
  const t = useTranslations("admin");
  const METRIC_ICONS = useMetricIcons();

  const metrics = stats
    ? [
        {
          key: "totalUsers",
          label: t("totalUsers"),
          value: stats.totalUsers.toLocaleString(),
        },
        {
          key: "totalOrgs",
          label: t("orgsCount"),
          value: stats.organizations.total.toLocaleString(),
        },
        {
          key: "pendingSignups",
          label: t("pendingSignups"),
          value: stats.pendingSignups.toLocaleString(),
        },
        {
          key: "recentOrders",
          label: t("ordersWeek"),
          value: stats.recentOrders.toLocaleString(),
        },
      ]
    : [];

  return (
    <AdminLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("usersTitle")}
          description={t("usersDescription")}
        />

        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="flex h-[120px] animate-pulse rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]"
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {metrics.map((metric) => {
              const style = METRIC_ICONS[metric.key];
              return (
                <div
                  key={metric.key}
                  className="flex flex-col gap-3 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] px-6 py-5"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-body text-[13px] text-[var(--muted-foreground)]">
                      {metric.label}
                    </span>
                    <div
                      className={cn(
                        "flex h-9 w-9 items-center justify-center rounded-[var(--radius-m)]",
                        style?.color
                      )}
                    >
                      <Icon name={style?.icon ?? "info"} size={20} className="text-white" />
                    </div>
                  </div>
                  <span className="font-brand text-[28px] font-bold text-[var(--foreground)]">
                    {metric.value}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex flex-col items-center gap-4 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] px-6 py-16">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[var(--secondary)]">
            <Icon
              name="engineering"
              size={32}
              className="text-[var(--muted-foreground)]"
            />
          </div>
          <div className="flex flex-col items-center gap-1">
            <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">
              {t("userManagementSoon")}
            </h2>
            <p className="max-w-md text-center font-body text-sm text-[var(--muted-foreground)]">
              {t("userManagementDescription")}
            </p>
          </div>
        </div>
      </div>
    </AdminLayout>
  );
}
