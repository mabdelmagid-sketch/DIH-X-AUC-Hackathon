"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { AdminLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";



const STATUS_STYLES: Record<string, string> = {
  pending:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  approved:
    "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  rejected: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

export default function SignupRequestsPage() {
  const t = useTranslations("admin");
  const tc = useTranslations("common");
  const [statusFilter, setStatusFilter] = useState("all");

  const STATUS_TABS = [
    { id: "all", label: tc("all") },
    { id: "pending", label: t("pending") },
    { id: "approved", label: t("approved") },
    { id: "rejected", label: t("rejected") },
  ];

  const { data, isLoading, refetch } =
    trpc.platformAdmin.signupRequests.list.useQuery({ limit: 50 });

  const approveMutation =
    trpc.platformAdmin.signupRequests.approve.useMutation({
      onSuccess: () => refetch(),
    });

  const rejectMutation = trpc.platformAdmin.signupRequests.reject.useMutation({
    onSuccess: () => refetch(),
  });

  const requests = useMemo(() => {
    if (!data?.requests) return [];
    if (statusFilter === "all") return data.requests;
    return data.requests.filter(
      (r: { status?: string }) => r.status?.toLowerCase() === statusFilter
    );
  }, [data, statusFilter]);

  const handleReject = (id: string) => {
    const reason = window.prompt(t("rejectionReason"));
    if (reason && reason.length >= 10) {
      rejectMutation.mutate({ id, reason });
    }
  };

  return (
    <AdminLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("signupRequests")}
          description={`${data?.total ?? 0} ${t("totalRequests")}`}
        />

        <div className="flex items-center gap-2">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={cn(
                "rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs transition-colors cursor-pointer",
                statusFilter === tab.id
                  ? "bg-[var(--primary)] font-medium text-white"
                  : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">
                {t("loadingRequests")}
              </span>
            </div>
          </div>
        ) : requests.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="how_to_reg" size={40} />
              <span className="font-body text-sm">{t("noRequests")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("businessName")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">Name</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">Email</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("date")}</th>
                  <th className="px-4 py-3 text-end font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {requests.map(
                  (
                    req: {
                      id: string;
                      organization_name?: string;
                      name?: string;
                      email?: string;
                      status?: string;
                      created_at?: string;
                    },
                    idx: number
                  ) => {
                    const status = (req.status ?? "PENDING").toLowerCase();
                    const isPending = status === "pending";

                    return (
                      <tr
                        key={req.id}
                        className={cn(
                          "bg-[var(--card)] transition-colors hover:bg-[var(--accent)]",
                          idx < requests.length - 1 &&
                            "border-b border-[var(--border)]"
                        )}
                      >
                        <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                          {req.organization_name ?? "—"}
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-[var(--foreground)]">
                          {req.name ?? "—"}
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                          {req.email ?? "—"}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={cn(
                              "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium capitalize",
                              STATUS_STYLES[status] ?? STATUS_STYLES.pending
                            )}
                          >
                            {status}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                          {req.created_at
                            ? new Date(req.created_at).toLocaleDateString(
                                "en-US",
                                { month: "short", day: "numeric", year: "numeric" }
                              )
                            : "—"}
                        </td>
                        <td className="px-4 py-3 text-end">
                          {isPending ? (
                            <div className="flex items-center justify-end gap-2">
                              <button
                                onClick={() =>
                                  approveMutation.mutate({ id: req.id })
                                }
                                disabled={approveMutation.isPending}
                                className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-green-100 px-3 py-1 font-body text-xs font-medium text-green-700 transition-colors hover:bg-green-200 disabled:opacity-50 cursor-pointer dark:bg-green-900/30 dark:text-green-400 dark:hover:bg-green-900/50"
                              >
                                <Icon name="check" size={14} />
                                {t("approve")}
                              </button>
                              <button
                                onClick={() => handleReject(req.id)}
                                disabled={rejectMutation.isPending}
                                className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-red-100 px-3 py-1 font-body text-xs font-medium text-red-700 transition-colors hover:bg-red-200 disabled:opacity-50 cursor-pointer dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50"
                              >
                                <Icon name="close" size={14} />
                                {t("reject")}
                              </button>
                            </div>
                          ) : (
                            <span className="font-body text-xs text-[var(--muted-foreground)]">
                              —
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  }
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AdminLayout>
  );
}
