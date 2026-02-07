"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";
import { useAuthStore } from "@/store/auth-store";

const STATUS_FILTERS = ["All", "AVAILABLE", "OCCUPIED", "RESERVED", "DIRTY"];

const useStatusLabels = (): Record<string, string> => {
  const t = useTranslations("tables");
  return {
    AVAILABLE: t("available"),
    OCCUPIED: t("occupied"),
    RESERVED: t("reserved"),
    DIRTY: t("dirty"),
  };
};

const STATUS_COLORS: Record<string, string> = {
  AVAILABLE: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  OCCUPIED: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  RESERVED: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  DIRTY: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

const TABLE_SHAPES = ["RECTANGLE", "SQUARE", "CIRCLE", "OVAL"] as const;

type MappedTable = {
  id: string;
  name: string;
  capacity: number;
  status: string;
  shape: string;
  updatedAt: string;
};

export default function TablesPage() {
  const locationId = useAuthStore((s) => s.location?.id);
  const [statusFilter, setStatusFilter] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [deletingTable, setDeletingTable] = useState<MappedTable | null>(null);
  const t = useTranslations("tables");
  const tc = useTranslations("common");
  const STATUS_LABELS = useStatusLabels();

  const utils = trpc.useUtils();

  const { data, isLoading } = trpc.tables.list.useQuery(
    {
      locationId: locationId!,
      ...(statusFilter !== "All" ? { status: statusFilter as "AVAILABLE" | "OCCUPIED" | "RESERVED" | "DIRTY" } : {}),
    },
    { enabled: !!locationId }
  );

  const tables = useMemo(() => {
    if (!data) return [];
    const mapped = (data as Array<{
      id: string;
      name: string;
      capacity: number;
      status: string;
      shape: string;
      pos_x: number;
      pos_y: number;
      width: number;
      height: number;
      created_at: string;
      updated_at: string;
    }>).map((t) => ({
      id: t.id,
      name: t.name,
      capacity: t.capacity,
      status: t.status,
      shape: t.shape,
      updatedAt: t.updated_at,
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.shape.toLowerCase().includes(q)
    );
  }, [data, searchQuery]);

  if (!locationId) {
    return (
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <PageHeader title={t("title")} description={t("description")} />
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="location_on" size={40} />
              <span className="font-body text-sm">{t("selectLocation")}</span>
            </div>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${tables.length} ${t("tablesAtLocation")}`}
          actions={
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90"
            >
              <Icon name="add" size={18} />
              {t("addTable")}
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
            {STATUS_FILTERS.map((status) => (
              <button
                key={status}
                onClick={() => setStatusFilter(status)}
                className={cn(
                  "rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs transition-colors",
                  statusFilter === status
                    ? "bg-[var(--primary)] font-medium text-white"
                    : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
                )}
              >
                {status === "All" ? tc("all") : STATUS_LABELS[status as keyof typeof STATUS_LABELS] ?? status}
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
        ) : tables.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="table_restaurant" size={40} />
              <span className="font-body text-sm">{t("noTables")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("tableName")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("capacity")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("shape")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("lastUpdated")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {tables.map((table, idx) => (
                  <tr
                    key={table.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                      idx < tables.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {table.name}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {table.capacity} {t("seats")}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)] capitalize">
                      {table.shape.toLowerCase()}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                          STATUS_COLORS[table.status] ?? STATUS_COLORS.AVAILABLE
                        )}
                      >
                        {STATUS_LABELS[table.status] ?? table.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {new Date(table.updatedAt).toLocaleString("en-US", {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                        hour12: true,
                      })}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setDeletingTable(table)}
                        className="rounded-full p-1.5 text-[var(--muted-foreground)] hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20 dark:hover:text-red-400 transition-colors"
                      >
                        <Icon name="delete" size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showAddModal && locationId && (
        <AddTableModal
          locationId={locationId}
          onClose={() => setShowAddModal(false)}
          onSuccess={() => { setShowAddModal(false); utils.tables.list.invalidate(); }}
        />
      )}

      {deletingTable && (
        <DeleteTableModal
          table={deletingTable}
          onClose={() => setDeletingTable(null)}
          onSuccess={() => { setDeletingTable(null); utils.tables.list.invalidate(); }}
        />
      )}
    </DashboardLayout>
  );
}

/* ─── Add Table Modal ───────────────────────────────── */

function AddTableModal({
  locationId,
  onClose,
  onSuccess,
}: {
  locationId: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState("4");
  const [shape, setShape] = useState("RECTANGLE");
  const [error, setError] = useState("");
  const t = useTranslations("tables");
  const tc = useTranslations("common");

  const createMutation = trpc.tables.create.useMutation({
    onError: (err) => setError(err.message),
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!name.trim()) { setError("Table name is required"); return; }

    await createMutation.mutateAsync({
      locationId,
      name: name.trim(),
      capacity: Number(capacity) || 4,
      shape: shape as typeof TABLE_SHAPES[number],
    });
    onSuccess();
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
            <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">{t("addTable")}</h2>
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
                {t("tableName")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Table 1" required
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("capacity")}</label>
                <input type="number" min="1" max="50" value={capacity} onChange={(e) => setCapacity(e.target.value)} placeholder="4"
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("shape")}</label>
                <select value={shape} onChange={(e) => setShape(e.target.value)}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]">
                  {TABLE_SHAPES.map((s) => (
                    <option key={s} value={s}>{t(s.toLowerCase() as 'rectangle' | 'square' | 'circle' | 'oval')}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button type="button" onClick={onClose}
                className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors">
                {tc("cancel")}
              </button>
              <button type="submit" disabled={createMutation.isPending || !name.trim()}
                className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50">
                {createMutation.isPending ? tc("creating") : t("addTable")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

/* ─── Delete Table Modal ────────────────────────────── */

function DeleteTableModal({
  table,
  onClose,
  onSuccess,
}: {
  table: MappedTable;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [error, setError] = useState("");
  const t = useTranslations("tables");
  const tc = useTranslations("common");
  const deleteMutation = trpc.tables.delete.useMutation({
    onError: (err) => setError(err.message),
  });

  const handleDelete = async () => {
    setError("");
    await deleteMutation.mutateAsync({ id: table.id });
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
            <h3 className="font-brand text-lg font-semibold text-[var(--foreground)]">{t("deleteTable")}</h3>
            <p className="font-body text-sm text-[var(--muted-foreground)]">
              {t("deleteConfirm")}
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
