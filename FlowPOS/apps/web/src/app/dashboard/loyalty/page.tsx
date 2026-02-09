"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

export default function LoyaltyPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const t = useTranslations("loyalty");
  const tc = useTranslations("common");

  const { data, isLoading } = trpc.loyalty.listMembers.useQuery({});

  const members = useMemo(() => {
    if (!data?.members) return [];
    const mapped = (data.members as Array<{
      id: string;
      customer_name: string;
      customer_email: string | null;
      customer_phone: string | null;
      points: number;
      total_points_earned: number;
      total_points_redeemed: number;
      store_credit: number;
      joined_at: string;
      last_activity: string | null;
      tags: string[];
      tier: { id: string; name: string; color: string | null } | null;
    }>).map((m) => ({
      id: m.id,
      name: m.customer_name,
      email: m.customer_email,
      phone: m.customer_phone,
      points: m.points ?? 0,
      totalEarned: m.total_points_earned ?? 0,
      storeCredit: m.store_credit ?? 0,
      tier: m.tier?.name ?? "None",
      tierColor: m.tier?.color ?? null,
      joinedAt: m.joined_at,
      lastActivity: m.last_activity,
      tags: m.tags ?? [],
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (m) =>
        m.name.toLowerCase().includes(q) ||
        (m.email?.toLowerCase().includes(q) ?? false) ||
        (m.phone?.toLowerCase().includes(q) ?? false) ||
        m.tier.toLowerCase().includes(q)
    );
  }, [data, searchQuery]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${data?.total ?? 0} ${t("members")}`}
        />

        {/* Search */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-sm">
            <Icon
              name="search"
              size={18}
              className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
            />
            <input
              type="text"
              placeholder={t("searchPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-10 w-full rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] ps-10 pe-4 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
            />
          </div>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">{t("loading")}</span>
            </div>
          </div>
        ) : members.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="loyalty" size={40} />
              <span className="font-body text-sm">{t("noMembers")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("member")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("contact")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("tier")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("points")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("totalEarned")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("storeCredit")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("lastActivity")}</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member, idx) => (
                  <tr
                    key={member.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                      idx < members.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {member.name}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {member.email || member.phone || "\u2014"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded-[var(--radius-pill)] bg-[var(--secondary)] px-2.5 py-0.5 font-body text-xs text-[var(--muted-foreground)]">
                        {member.tier}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {member.points.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {member.totalEarned.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {member.storeCredit > 0 ? `${(member.storeCredit / 100).toFixed(2)}` : "\u2014"}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {member.lastActivity
                        ? new Date(member.lastActivity).toLocaleString("en-US", {
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                            hour12: true,
                          })
                        : "\u2014"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
