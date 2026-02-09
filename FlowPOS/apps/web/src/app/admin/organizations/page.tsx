"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { AdminLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const useStatusTabs = () => {
  const t = useTranslations("common");
  const ta = useTranslations("admin");
  return [
    { id: "all", label: t("all") },
    { id: "active", label: t("active") },
    { id: "suspended", label: ta("suspended") },
  ];
};

const STATUS_STYLES: Record<string, string> = {
  active:
    "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  suspended:
    "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  pending:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

export default function OrganizationsPage() {
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const t = useTranslations("admin");
  const tc = useTranslations("common");
  const STATUS_TABS = useStatusTabs();

  const { data, isLoading, refetch } =
    trpc.platformAdmin.organizations.list.useQuery({ limit: 50 });

  const suspendMutation = trpc.platformAdmin.organizations.suspend.useMutation({
    onSuccess: () => refetch(),
  });

  const activateMutation =
    trpc.platformAdmin.organizations.activate.useMutation({
      onSuccess: () => refetch(),
    });

  const organizations = useMemo(() => {
    if (!data?.organizations) return [];
    let filtered = data.organizations;

    if (statusFilter !== "all") {
      filtered = filtered.filter(
        (org: { status?: string }) =>
          org.status?.toLowerCase() === statusFilter
      );
    }

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter((org: { name?: string }) =>
        org.name?.toLowerCase().includes(q)
      );
    }

    return filtered;
  }, [data, statusFilter, searchQuery]);

  const handleSuspend = (id: string) => {
    const reason = window.prompt(t("suspensionReason"));
    if (reason && reason.length >= 10) {
      suspendMutation.mutate({ id, reason });
    }
  };

  return (
    <AdminLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("organizations")}
          description={`${data?.total ?? 0} ${t("registeredOrgs")}`}
          actions={
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 cursor-pointer"
            >
              <Icon name="add" size={18} />
              {t("createOrg")}
            </button>
          }
        />

        {/* Filters */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="relative flex-1 max-w-sm">
            <Icon
              name="search"
              size={18}
              className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
            />
            <input
              type="text"
              placeholder={t("searchByName")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-10 w-full rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] ps-10 pe-4 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
            />
          </div>

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
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">
                {t("loadingOrgs")}
              </span>
            </div>
          </div>
        ) : organizations.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="business" size={40} />
              <span className="font-body text-sm">{t("noOrgs")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("name")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("slug")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("users")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("orders")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("created")}</th>
                  <th className="px-4 py-3 text-end font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {organizations.map(
                  (
                    org: {
                      id: string;
                      name?: string;
                      slug?: string;
                      status?: string;
                      users?: { count: number }[];
                      orders?: { count: number }[];
                      created_at?: string;
                    },
                    idx: number
                  ) => {
                    const status = (org.status ?? "ACTIVE").toUpperCase();
                    const isActive = status === "ACTIVE";
                    const userCount = org.users?.[0]?.count ?? 0;
                    const orderCount = org.orders?.[0]?.count ?? 0;

                    return (
                      <tr
                        key={org.id}
                        className={cn(
                          "bg-[var(--card)] transition-colors hover:bg-[var(--accent)]",
                          idx < organizations.length - 1 &&
                            "border-b border-[var(--border)]"
                        )}
                      >
                        <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                          {org.name ?? "Unnamed"}
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                          {org.slug ?? "—"}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={cn(
                              "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium capitalize",
                              STATUS_STYLES[status.toLowerCase()] ?? STATUS_STYLES.active
                            )}
                          >
                            {status.toLowerCase()}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                          {userCount}
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                          {orderCount}
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                          {org.created_at
                            ? new Date(org.created_at).toLocaleDateString(
                                "en-US",
                                { month: "short", day: "numeric", year: "numeric" }
                              )
                            : "—"}
                        </td>
                        <td className="px-4 py-3 text-end">
                          {isActive ? (
                            <button
                              onClick={() => handleSuspend(org.id)}
                              disabled={suspendMutation.isPending}
                              className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-red-100 px-3 py-1 font-body text-xs font-medium text-red-700 transition-colors hover:bg-red-200 disabled:opacity-50 cursor-pointer dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50"
                            >
                              <Icon name="block" size={14} />
                              {t("suspend")}
                            </button>
                          ) : (
                            <button
                              onClick={() =>
                                activateMutation.mutate({ id: org.id })
                              }
                              disabled={activateMutation.isPending}
                              className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-green-100 px-3 py-1 font-body text-xs font-medium text-green-700 transition-colors hover:bg-green-200 disabled:opacity-50 cursor-pointer dark:bg-green-900/30 dark:text-green-400 dark:hover:bg-green-900/50"
                            >
                              <Icon name="check_circle" size={14} />
                              {t("activate")}
                            </button>
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

      {showCreateModal && (
        <CreateOrgModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false);
            refetch();
          }}
        />
      )}
    </AdminLayout>
  );
}

/* ─── Create Organization Modal ────────────────────────── */

function CreateOrgModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [plan, setPlan] = useState<"free" | "pro" | "enterprise">("free");
  const [error, setError] = useState("");
  const t = useTranslations("admin");
  const tc = useTranslations("common");

  const createMutation =
    trpc.platformAdmin.organizations.create.useMutation({
      onSuccess: () => onSuccess(),
      onError: (err) => setError(err.message),
    });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!name || !ownerName || !ownerEmail || !ownerPassword) {
      setError(t("allFieldsRequired"));
      return;
    }
    if (ownerPassword.length < 8) {
      setError(t("passwordMinLength"));
      return;
    }

    createMutation.mutate({
      name,
      ownerName,
      ownerEmail,
      ownerPassword,
      plan,
    });
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-md rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
            <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">
              {t("createOrg")}
            </h2>
            <button
              onClick={onClose}
              className="rounded-full p-1 text-[var(--muted-foreground)] hover:bg-[var(--accent)] cursor-pointer"
            >
              <Icon name="close" size={20} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-6 py-5">
            {error && (
              <div className="rounded-[var(--radius-m)] bg-red-50 px-3 py-2 font-body text-xs text-red-600 dark:bg-red-900/20 dark:text-red-400">
                {error}
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {t("businessName")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("orgNamePlaceholder")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {t("ownerName")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="text"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                placeholder={t("ownerNamePlaceholder")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {t("ownerEmail")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="email"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                placeholder={t("ownerEmailPlaceholder")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {t("ownerPassword")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="password"
                value={ownerPassword}
                onChange={(e) => setOwnerPassword(e.target.value)}
                placeholder={t("passwordPlaceholder")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("plan")}</label>
              <select
                value={plan}
                onChange={(e) => setPlan(e.target.value as "free" | "pro" | "enterprise")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              >
                <option value="free">{t("free")}</option>
                <option value="pro">{t("pro")}</option>
                <option value="enterprise">{t("enterprise")}</option>
              </select>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors cursor-pointer"
              >
                {tc("cancel")}
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50 cursor-pointer"
              >
                {createMutation.isPending ? tc("creating") : t("createOrg")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
