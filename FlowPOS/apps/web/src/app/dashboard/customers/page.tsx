"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { trpc } from "@/lib/trpc";
import { formatCurrency, cn } from "@/lib/utils";

type Customer = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  notes: string | null;
  loyalty_points: number | null;
  total_spent: number | null;
  visit_count: number | null;
  created_at: string | null;
};

type SortField = "name" | "total_spent" | "visit_count" | "created_at";

export default function CustomersPage() {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortField>("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const t = useTranslations("customers");
  const tc = useTranslations("common");

  const utils = trpc.useUtils();

  const { data, isLoading } = trpc.customers.list.useQuery({
    search: search || undefined,
    limit: 100,
    sortBy,
    sortDir,
  });

  const { data: stats } = trpc.customers.stats.useQuery();

  const customers = data?.customers ?? [];

  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("asc");
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortBy !== field) return <Icon name="unfold_more" size={14} className="text-[var(--muted-foreground)] opacity-0 group-hover:opacity-100 transition-opacity" />;
    return <Icon name={sortDir === "asc" ? "arrow_upward" : "arrow_downward"} size={14} className="text-[var(--primary)]" />;
  };

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={t("description")}
          actions={
            <button
              onClick={() => setShowAddModal(true)}
              className="inline-flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90"
            >
              <Icon name="person_add" size={16} />
              {t("addCustomer")}
            </button>
          }
        />

        {/* Stats Row */}
        {stats && (
          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col gap-1 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-4">
              <span className="font-body text-xs text-[var(--muted-foreground)]">{t("totalCustomers")}</span>
              <span className="font-brand text-2xl font-bold text-[var(--foreground)]">{stats.totalCustomers}</span>
            </div>
            <div className="flex flex-col gap-1 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-4">
              <span className="font-body text-xs text-[var(--muted-foreground)]">{t("newThisMonth")}</span>
              <span className="font-brand text-2xl font-bold text-[var(--foreground)]">{stats.newThisMonth}</span>
            </div>
            <div className="flex flex-col gap-1 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-4">
              <span className="font-body text-xs text-[var(--muted-foreground)]">{t("topSpender")}</span>
              <span className="font-brand text-2xl font-bold text-[var(--foreground)]">
                {stats.topSpenders[0]?.name?.split(" ")[0] ?? "—"}
              </span>
            </div>
          </div>
        )}

        {/* Search */}
        <div className="relative">
          <Icon
            name="search"
            size={18}
            className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
          />
          <input
            type="text"
            placeholder={t("searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-10 w-full rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--card)] ps-10 pe-4 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
          />
        </div>

        {/* Table */}
        <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
            </div>
          ) : customers.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-20">
              <Icon name="people" size={40} className="text-[var(--muted-foreground)]" />
              <p className="font-body text-sm text-[var(--muted-foreground)]">
                {search ? t("noMatch") : t("noCustomers")}
              </p>
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--background)]">
                  <th className="px-4 py-3 text-start">
                    <button onClick={() => handleSort("name")} className="group flex items-center gap-1 font-brand text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                      {tc("name")} <SortIcon field="name" />
                    </button>
                  </th>
                  <th className="px-4 py-3 text-start font-brand text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                    {t("contact")}
                  </th>
                  <th className="px-4 py-3 text-start">
                    <button onClick={() => handleSort("visit_count")} className="group flex items-center gap-1 font-brand text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                      {t("totalVisits")} <SortIcon field="visit_count" />
                    </button>
                  </th>
                  <th className="px-4 py-3 text-start">
                    <button onClick={() => handleSort("total_spent")} className="group flex items-center gap-1 font-brand text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                      {t("totalSpent")} <SortIcon field="total_spent" />
                    </button>
                  </th>
                  <th className="px-4 py-3 text-start font-brand text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                    {t("points")}
                  </th>
                  <th className="px-4 py-3 text-start">
                    <button onClick={() => handleSort("created_at")} className="group flex items-center gap-1 font-brand text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                      {t("joined")} <SortIcon field="created_at" />
                    </button>
                  </th>
                  <th className="px-4 py-3 text-end font-brand text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                    {tc("actions")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {customers.map((customer: Customer, idx: number) => (
                  <tr
                    key={customer.id}
                    className={cn(
                      "transition-colors hover:bg-[var(--accent)]",
                      idx < customers.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-xs font-bold text-white">
                          {customer.name.charAt(0).toUpperCase()}
                        </div>
                        <span className="font-body text-sm font-medium text-[var(--foreground)]">{customer.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-0.5">
                        {customer.email && (
                          <span className="font-body text-xs text-[var(--muted-foreground)]">{customer.email}</span>
                        )}
                        {customer.phone && (
                          <span className="font-body text-xs text-[var(--muted-foreground)]">{customer.phone}</span>
                        )}
                        {!customer.email && !customer.phone && (
                          <span className="font-body text-xs text-[var(--muted-foreground)]">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--foreground)]">
                      {customer.visit_count ?? 0}
                    </td>
                    <td className="px-4 py-3 font-body text-sm font-medium text-[var(--foreground)]">
                      {formatCurrency(customer.total_spent ?? 0)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-[var(--color-success)] px-2 py-0.5 font-body text-xs font-medium text-[var(--color-success-foreground)]">
                        <Icon name="star" size={12} />
                        {customer.loyalty_points ?? 0}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-body text-xs text-[var(--muted-foreground)]">
                      {customer.created_at
                        ? new Date(customer.created_at).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => setEditingCustomer(customer)}
                          className="rounded-full p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--accent)] hover:text-[var(--foreground)]"
                        >
                          <Icon name="edit" size={16} />
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(customer.id)}
                          className="rounded-full p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20"
                        >
                          <Icon name="delete" size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {/* Footer with count */}
          {!isLoading && customers.length > 0 && (
            <div className="border-t border-[var(--border)] px-4 py-3">
              <span className="font-body text-xs text-[var(--muted-foreground)]">
                {tc("showing")} {customers.length} {tc("of")} {data?.total ?? 0} {t("customers")}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Add / Edit Modal */}
      {(showAddModal || editingCustomer) && (
        <CustomerModal
          customer={editingCustomer}
          onClose={() => {
            setShowAddModal(false);
            setEditingCustomer(null);
          }}
          onSuccess={() => {
            setShowAddModal(false);
            setEditingCustomer(null);
            utils.customers.list.invalidate();
            utils.customers.stats.invalidate();
          }}
        />
      )}

      {/* Delete Confirmation */}
      {deleteConfirm && (
        <DeleteConfirmModal
          customerId={deleteConfirm}
          onClose={() => setDeleteConfirm(null)}
          onSuccess={() => {
            setDeleteConfirm(null);
            utils.customers.list.invalidate();
            utils.customers.stats.invalidate();
          }}
        />
      )}
    </DashboardLayout>
  );
}

/* ─── Add / Edit Customer Modal ────────────────────────── */

function CustomerModal({
  customer,
  onClose,
  onSuccess,
}: {
  customer: Customer | null;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const isEdit = !!customer;
  const [name, setName] = useState(customer?.name ?? "");
  const [email, setEmail] = useState(customer?.email ?? "");
  const [phone, setPhone] = useState(customer?.phone ?? "");
  const [notes, setNotes] = useState(customer?.notes ?? "");
  const t = useTranslations("customers");
  const tc = useTranslations("common");

  const createCustomer = trpc.customers.create.useMutation();
  const updateCustomer = trpc.customers.update.useMutation();
  const isPending = createCustomer.isPending || updateCustomer.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    if (isEdit && customer) {
      await updateCustomer.mutateAsync({
        id: customer.id,
        name: name.trim(),
        email: email.trim() || null,
        phone: phone.trim() || null,
        notes: notes.trim() || null,
      });
    } else {
      await createCustomer.mutateAsync({
        name: name.trim(),
        email: email.trim() || null,
        phone: phone.trim() || null,
        notes: notes.trim() || null,
      });
    }
    onSuccess();
  };

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-md rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
            <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">
              {isEdit ? t("editCustomer") : t("addCustomer")}
            </h2>
            <button onClick={onClose} className="rounded-full p-1 text-[var(--muted-foreground)] hover:bg-[var(--accent)]">
              <Icon name="close" size={20} />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-6 py-5">
            {/* Name */}
            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {tc("name")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("customerName")}
                required
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            {/* Email */}
            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">{tc("email")}</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="customer@example.com"
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            {/* Phone */}
            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">{tc("phone")}</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+966 5XX XXX XXXX"
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            {/* Notes */}
            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">{tc("notes")}</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder={t("additionalNotes")}
                rows={3}
                className="rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 py-2 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] resize-none"
              />
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
              >
                {tc("cancel")}
              </button>
              <button
                type="submit"
                disabled={isPending || !name.trim()}
                className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50"
              >
                {isPending
                  ? isEdit
                    ? tc("saving")
                    : tc("creating")
                  : isEdit
                    ? t("saveChanges")
                    : t("addCustomer")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

/* ─── Delete Confirmation Modal ────────────────────────── */

function DeleteConfirmModal({
  customerId,
  onClose,
  onSuccess,
}: {
  customerId: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("customers");
  const tc = useTranslations("common");
  const deleteCustomer = trpc.customers.delete.useMutation();

  const handleDelete = async () => {
    await deleteCustomer.mutateAsync({ id: customerId });
    onSuccess();
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-sm rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-6 shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex flex-col items-center gap-4 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
              <Icon name="delete" size={24} className="text-red-600 dark:text-red-400" />
            </div>
            <div>
              <h3 className="font-brand text-lg font-semibold text-[var(--foreground)]">{t("deleteCustomer")}</h3>
              <p className="mt-1 font-body text-sm text-[var(--muted-foreground)]">
                {t("deleteConfirm")}
              </p>
            </div>
            <div className="flex w-full gap-3">
              <button
                onClick={onClose}
                className="flex-1 rounded-[var(--radius-pill)] border border-[var(--border)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
              >
                {tc("cancel")}
              </button>
              <button
                onClick={handleDelete}
                disabled={deleteCustomer.isPending}
                className="flex-1 rounded-[var(--radius-pill)] bg-[var(--destructive)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--destructive)]/90 disabled:opacity-50"
              >
                {deleteCustomer.isPending ? tc("deleting") : tc("delete")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
