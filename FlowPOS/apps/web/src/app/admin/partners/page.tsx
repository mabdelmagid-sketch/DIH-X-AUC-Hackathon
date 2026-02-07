"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { AdminLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const STATUS_TABS = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "suspended", label: "Suspended" },
];

const STATUS_STYLES: Record<string, string> = {
  active:
    "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  suspended:
    "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

export default function PartnersPage() {
  const t = useTranslations("admin");
  const tc = useTranslations("common");
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const { data, isLoading, refetch } =
    trpc.platformAdmin.partners.list.useQuery({ limit: 50 });

  const suspendMutation = trpc.platformAdmin.partners.suspend.useMutation({
    onSuccess: () => refetch(),
  });

  const activateMutation = trpc.platformAdmin.partners.activate.useMutation({
    onSuccess: () => refetch(),
  });

  const partners = useMemo(() => {
    if (!data?.partners) return [];
    let filtered = data.partners;

    if (statusFilter !== "all") {
      filtered = filtered.filter(
        (p: { status?: string }) => p.status?.toLowerCase() === statusFilter
      );
    }

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter((p: { name?: string }) =>
        p.name?.toLowerCase().includes(q)
      );
    }

    return filtered;
  }, [data, statusFilter, searchQuery]);

  const handleSuspend = (id: string) => {
    const reason = window.prompt("Enter suspension reason (min 10 characters):");
    if (reason && reason.length >= 10) {
      suspendMutation.mutate({ id, reason });
    }
  };

  return (
    <AdminLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("partners")}
          description={`${data?.total ?? 0} ${t("registeredPartners")}`}
          actions={
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 cursor-pointer"
            >
              <Icon name="add" size={18} />
              {t("addPartner")}
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
                {t("loadingPartners")}
              </span>
            </div>
          </div>
        ) : partners.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="handshake" size={40} />
              <span className="font-body text-sm">{t("noPartners")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("partnerName")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("contactEmail")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("commission")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("orgs")}</th>
                  <th className="px-4 py-3 text-end font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {partners.map(
                  (
                    partner: {
                      id: string;
                      name?: string;
                      contact_email?: string;
                      status?: string;
                      commission_rate?: number;
                      partner_organizations?: { count: number }[];
                    },
                    idx: number
                  ) => {
                    const status = (partner.status ?? "ACTIVE").toUpperCase();
                    const isActive = status === "ACTIVE";
                    const orgCount = partner.partner_organizations?.[0]?.count ?? 0;

                    return (
                      <tr
                        key={partner.id}
                        className={cn(
                          "bg-[var(--card)] transition-colors hover:bg-[var(--accent)]",
                          idx < partners.length - 1 &&
                            "border-b border-[var(--border)]"
                        )}
                      >
                        <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                          {partner.name ?? "—"}
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                          {partner.contact_email ?? "—"}
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
                        <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                          {partner.commission_rate != null
                            ? `${partner.commission_rate}%`
                            : "—"}
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                          {orgCount}
                        </td>
                        <td className="px-4 py-3 text-end">
                          {isActive ? (
                            <button
                              onClick={() => handleSuspend(partner.id)}
                              disabled={suspendMutation.isPending}
                              className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-red-100 px-3 py-1 font-body text-xs font-medium text-red-700 transition-colors hover:bg-red-200 disabled:opacity-50 cursor-pointer dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50"
                            >
                              <Icon name="block" size={14} />
                              {t("suspend")}
                            </button>
                          ) : (
                            <button
                              onClick={() =>
                                activateMutation.mutate({ id: partner.id })
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
        <CreatePartnerModal
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

/* ─── Create Partner Modal ─────────────────────────────── */

function CreatePartnerModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("admin");
  const tc = useTranslations("common");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [commissionRate, setCommissionRate] = useState("10");
  const [error, setError] = useState("");

  const createMutation = trpc.platformAdmin.partners.create.useMutation({
    onSuccess: () => onSuccess(),
    onError: (err) => setError(err.message),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!name || !slug || !contactEmail) {
      setError(t("fieldsRequired"));
      return;
    }

    createMutation.mutate({
      name,
      slug,
      contactEmail,
      commissionRate: Number(commissionRate) || 10,
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
              {t("addPartner")}
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
                {t("partnerName")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (!slug) setSlug(e.target.value.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, ""));
                }}
                placeholder={t("partnerNamePlaceholder")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {t("partnerSlug")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                placeholder={t("slugPlaceholder")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {t("contactEmail")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="email"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                placeholder={t("contactEmailPlaceholder")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("commissionRate")}</label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={commissionRate}
                onChange={(e) => setCommissionRate(e.target.value)}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
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
                {createMutation.isPending ? tc("creating") : t("createPartner")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
