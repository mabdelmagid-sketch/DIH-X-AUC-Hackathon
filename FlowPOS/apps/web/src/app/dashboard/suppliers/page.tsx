"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

type MappedSupplier = {
  id: string;
  name: string;
  contactName: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  paymentTerms: string | null;
  notes: string | null;
  isActive: boolean;
};

export default function SuppliersPage() {
  const t = useTranslations("suppliers");
  const tc = useTranslations("common");

  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "inactive">("all");
  const [editingSupplier, setEditingSupplier] = useState<MappedSupplier | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [deletingSupplier, setDeletingSupplier] = useState<MappedSupplier | null>(null);

  const utils = trpc.useUtils();
  const { data, isLoading } = trpc.suppliers.list.useQuery({
    ...(activeFilter === "active" ? { isActive: true } : activeFilter === "inactive" ? { isActive: false } : {}),
    limit: 50,
  });

  const suppliers = useMemo(() => {
    if (!data?.suppliers) return [];
    const mapped: MappedSupplier[] = (data.suppliers as Array<{
      id: string;
      name: string;
      contact_name: string | null;
      email: string | null;
      phone: string | null;
      address: string | null;
      payment_terms: string | null;
      notes: string | null;
      is_active: boolean;
    }>).map((s) => ({
      id: s.id,
      name: s.name,
      contactName: s.contact_name,
      email: s.email,
      phone: s.phone,
      address: s.address,
      paymentTerms: s.payment_terms,
      notes: s.notes,
      isActive: s.is_active,
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.contactName?.toLowerCase().includes(q) ?? false) ||
        (s.email?.toLowerCase().includes(q) ?? false) ||
        (s.phone?.toLowerCase().includes(q) ?? false)
    );
  }, [data, searchQuery]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${data?.total ?? 0} ${t("suppliersCount")}`}
          actions={
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90"
            >
              <Icon name="add" size={18} />
              {t("addSupplier")}
            </button>
          }
        />

        {/* Filters */}
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
          <div className="flex items-center gap-2">
            {(["all", "active", "inactive"] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setActiveFilter(filter)}
                className={cn(
                  "rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs capitalize transition-colors",
                  activeFilter === filter
                    ? "bg-[var(--primary)] font-medium text-white"
                    : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
                )}
              >
                {filter}
              </button>
            ))}
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
        ) : suppliers.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="local_shipping" size={40} />
              <span className="font-body text-sm">{t("noSuppliers")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("supplierName")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("contactName")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("email")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("phone")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("paymentTerms")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("status")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((supplier, idx) => (
                  <tr
                    key={supplier.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                      idx < suppliers.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {supplier.name}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {supplier.contactName ?? "\u2014"}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {supplier.email ?? "\u2014"}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {supplier.phone ?? "\u2014"}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {supplier.paymentTerms ?? "\u2014"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                          supplier.isActive
                            ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                            : "bg-[var(--secondary)] text-[var(--muted-foreground)]"
                        )}
                      >
                        {supplier.isActive ? t("active") : t("inactive")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setEditingSupplier(supplier)}
                          className="rounded-full p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)] transition-colors"
                        >
                          <Icon name="edit" size={16} />
                        </button>
                        <button
                          onClick={() => setDeletingSupplier(supplier)}
                          className="rounded-full p-1.5 text-[var(--muted-foreground)] hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20 dark:hover:text-red-400 transition-colors"
                        >
                          <Icon name="delete" size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add / Edit Modal */}
      {(showAddModal || editingSupplier) && (
        <SupplierModal
          supplier={editingSupplier}
          onClose={() => { setShowAddModal(false); setEditingSupplier(null); }}
          onSuccess={() => {
            setShowAddModal(false);
            setEditingSupplier(null);
            utils.suppliers.list.invalidate();
          }}
        />
      )}

      {/* Delete Confirmation */}
      {deletingSupplier && (
        <DeleteConfirmModal
          supplier={deletingSupplier}
          onClose={() => setDeletingSupplier(null)}
          onSuccess={() => {
            setDeletingSupplier(null);
            utils.suppliers.list.invalidate();
          }}
        />
      )}
    </DashboardLayout>
  );
}

/* ─── Supplier Modal (Add / Edit) ───────────────────── */

function SupplierModal({
  supplier,
  onClose,
  onSuccess,
}: {
  supplier: MappedSupplier | null;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("suppliers");
  const tc = useTranslations("common");
  const isEdit = !!supplier;
  const [name, setName] = useState(supplier?.name ?? "");
  const [contactName, setContactName] = useState(supplier?.contactName ?? "");
  const [email, setEmail] = useState(supplier?.email ?? "");
  const [phone, setPhone] = useState(supplier?.phone ?? "");
  const [address, setAddress] = useState(supplier?.address ?? "");
  const [paymentTerms, setPaymentTerms] = useState(supplier?.paymentTerms ?? "");
  const [notes, setNotes] = useState(supplier?.notes ?? "");
  const [isActive, setIsActive] = useState(supplier?.isActive ?? true);
  const [error, setError] = useState("");

  const createMutation = trpc.suppliers.create.useMutation({ onError: (err) => setError(err.message) });
  const updateMutation = trpc.suppliers.update.useMutation({ onError: (err) => setError(err.message) });
  const isPending = createMutation.isPending || updateMutation.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!name.trim()) { setError(t("supplierNameRequired")); return; }

    const payload = {
      name: name.trim(),
      contactName: contactName.trim() || undefined,
      email: email.trim() || "",
      phone: phone.trim() || undefined,
      address: address.trim() || undefined,
      paymentTerms: paymentTerms.trim() || undefined,
      notes: notes.trim() || undefined,
      isActive,
    };

    if (isEdit) {
      await updateMutation.mutateAsync({ id: supplier.id, ...payload });
    } else {
      await createMutation.mutateAsync(payload);
    }
    onSuccess();
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-lg rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
            <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">
              {isEdit ? t("editSupplier") : t("addSupplier")}
            </h2>
            <button onClick={onClose} className="rounded-full p-1 text-[var(--muted-foreground)] hover:bg-[var(--accent)]">
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
                {t("supplierName")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("companyName")} required
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("contactName")}</label>
                <input type="text" value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder={t("contactPerson")}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("email")}</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("emailPlaceholder")}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("phone")}</label>
                <input type="text" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder={t("phonePlaceholder")}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("paymentTerms")}</label>
                <input type="text" value={paymentTerms} onChange={(e) => setPaymentTerms(e.target.value)} placeholder={t("paymentTermsPlaceholder")}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("address")}</label>
              <input type="text" value={address} onChange={(e) => setAddress(e.target.value)} placeholder={t("addressPlaceholder")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("notes")}</label>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={t("notesPlaceholder")} rows={2}
                className="rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 py-2 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] resize-none" />
            </div>

            {isEdit && (
              <label className="flex items-center gap-2 cursor-pointer">
                <div
                  onClick={() => setIsActive(!isActive)}
                  className={cn(
                    "relative h-5 w-9 rounded-full transition-colors cursor-pointer",
                    isActive ? "bg-[var(--primary)]" : "bg-[var(--muted-foreground)]/30"
                  )}
                >
                  <div className={cn(
                    "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                    isActive ? "translate-x-4" : "translate-x-0.5"
                  )} />
                </div>
                <span className="font-body text-sm text-[var(--foreground)]">{t("active")}</span>
              </label>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <button type="button" onClick={onClose}
                className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors">
                {tc("cancel")}
              </button>
              <button type="submit" disabled={isPending || !name.trim()}
                className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50">
                {isPending ? tc("saving") : isEdit ? tc("save") : t("addSupplier")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

/* ─── Delete Confirmation Modal ─────────────────────── */

function DeleteConfirmModal({
  supplier,
  onClose,
  onSuccess,
}: {
  supplier: MappedSupplier;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("suppliers");
  const tc = useTranslations("common");
  const [error, setError] = useState("");
  const deleteMutation = trpc.suppliers.delete.useMutation({ onError: (err) => setError(err.message) });

  const handleDelete = async () => {
    setError("");
    await deleteMutation.mutateAsync({ id: supplier.id });
    onSuccess();
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl" onClick={(e) => e.stopPropagation()}>
          <div className="flex flex-col items-center gap-3 px-6 py-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
              <Icon name="warning" size={24} className="text-red-600 dark:text-red-400" />
            </div>
            <h3 className="font-brand text-lg font-semibold text-[var(--foreground)]">{t("deleteSupplier")}</h3>
            <p className="font-body text-sm text-[var(--muted-foreground)]">
              {t("deleteConfirm", { name: supplier.name })}
            </p>
            {error && (
              <div className="w-full rounded-[var(--radius-m)] bg-red-50 px-3 py-2 font-body text-xs text-red-600 dark:bg-red-900/20 dark:text-red-400">
                {error}
              </div>
            )}
          </div>
          <div className="flex items-center justify-end gap-3 border-t border-[var(--border)] px-6 py-4">
            <button onClick={onClose}
              className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors">
              {tc("cancel")}
            </button>
            <button onClick={handleDelete} disabled={deleteMutation.isPending}
              className="rounded-[var(--radius-pill)] bg-[var(--destructive)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--destructive)]/90 disabled:opacity-50">
              {deleteMutation.isPending ? tc("deleting") : tc("delete")}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
