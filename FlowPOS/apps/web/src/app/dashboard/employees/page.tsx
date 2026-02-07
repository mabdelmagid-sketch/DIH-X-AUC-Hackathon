"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const ROLES = ["OWNER", "ADMIN", "MANAGER", "STAFF", "KITCHEN"] as const;

const ROLE_COLORS: Record<string, string> = {
  OWNER: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  ADMIN: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  MANAGER: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  STAFF: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  KITCHEN: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
};

type MappedEmployee = {
  id: string;
  name: string;
  email: string;
  role: string;
  location: string;
  isActive: boolean;
  hourlyRate: number | null;
};

export default function EmployeesPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const t = useTranslations("employees");
  const tc = useTranslations("common");

  const utils = trpc.useUtils();
  const { data: employees, isLoading } = trpc.employees.list.useQuery({});

  const filtered = useMemo(() => {
    if (!employees) return [];
    const mapped: MappedEmployee[] = employees.map((e: {
      id: string;
      is_active: boolean;
      hourly_rate: number | null;
      user: { email: string; name: string | null } | null;
      role: string | null;
      location: { name: string } | null;
    }) => ({
      id: e.id,
      name: e.user?.name ?? "Unknown",
      email: e.user?.email ?? "",
      role: e.role ?? "STAFF",
      location: e.location?.name ?? "—",
      isActive: e.is_active,
      hourlyRate: e.hourly_rate,
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.email.toLowerCase().includes(q) ||
        e.role.toLowerCase().includes(q)
    );
  }, [employees, searchQuery]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${employees?.length ?? 0} ${t("teamMembers")}`}
          actions={
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90"
            >
              <Icon name="person_add" size={18} />
              {t("addEmployee")}
            </button>
          }
        />

        {/* Search */}
        <div className="relative max-w-sm">
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

        {/* Table */}
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">{t("loading")}</span>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="badge" size={40} />
              <span className="font-body text-sm">{t("noEmployees")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("employee")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("email")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("role")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("location")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((emp, idx) => (
                  <tr
                    key={emp.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors cursor-pointer",
                      idx < filtered.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--primary)] text-xs font-medium text-white">
                          {emp.name.split(" ").map((w: string) => w[0]).join("").toUpperCase().slice(0, 2)}
                        </div>
                        <span className="font-brand text-sm font-medium text-[var(--foreground)]">
                          {emp.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {emp.email}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                        ROLE_COLORS[emp.role] ?? ROLE_COLORS.STAFF
                      )}>
                        {emp.role}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {emp.location}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "inline-flex h-2 w-2 rounded-full",
                        emp.isActive ? "bg-green-500" : "bg-[var(--muted-foreground)]"
                      )} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Employee Modal */}
      {showAddModal && (
        <AddEmployeeModal
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            setShowAddModal(false);
            utils.employees.list.invalidate();
          }}
        />
      )}
    </DashboardLayout>
  );
}

/* ─── Add Employee Modal ──────────────────────────────── */

function AddEmployeeModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<string>("STAFF");
  const [pin, setPin] = useState("");
  const [hourlyRate, setHourlyRate] = useState("");
  const [error, setError] = useState("");
  const t = useTranslations("employees");
  const tc = useTranslations("common");

  const { data: locations } = trpc.locations.list.useQuery();
  const [locationId, setLocationId] = useState("");

  // Auto-select first location when loaded
  const firstLocation = locations?.[0];
  if (firstLocation && !locationId) {
    setLocationId(firstLocation.id);
  }

  const createEmployee = trpc.employees.create.useMutation({
    onError: (err) => setError(err.message),
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!name.trim() || !email.trim() || !locationId) {
      setError("Name, email, and location are required");
      return;
    }

    await createEmployee.mutateAsync({
      name: name.trim(),
      email: email.trim(),
      role: role as typeof ROLES[number],
      locationId,
      pin: pin.trim() || null,
      hourlyRate: hourlyRate ? Math.round(Number(hourlyRate) * 100) : null,
    });

    onSuccess();
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-md rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
            <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">
              {t("addEmployee")}
            </h2>
            <button onClick={onClose} className="rounded-full p-1 text-[var(--muted-foreground)] hover:bg-[var(--accent)]">
              <Icon name="close" size={20} />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-6 py-5">
            {error && (
              <div className="rounded-[var(--radius-m)] bg-red-50 px-3 py-2 font-body text-xs text-red-600 dark:bg-red-900/20 dark:text-red-400">
                {error}
              </div>
            )}

            {/* Name */}
            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {tc("name")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("fullName")}
                required
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            {/* Email */}
            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {tc("email")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("emailPlaceholder")}
                required
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            {/* Role + Location row */}
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">
                  {tc("role")} <span className="text-[var(--destructive)]">*</span>
                </label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">
                  {t("location")} <span className="text-[var(--destructive)]">*</span>
                </label>
                <select
                  value={locationId}
                  onChange={(e) => setLocationId(e.target.value)}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
                >
                  {!locations ? (
                    <option value="">{tc("loading")}</option>
                  ) : (
                    locations.map((loc: { id: string; name: string }) => (
                      <option key={loc.id} value={loc.id}>{loc.name}</option>
                    ))
                  )}
                </select>
              </div>
            </div>

            {/* PIN + Hourly Rate row */}
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("pin")}</label>
                <input
                  type="text"
                  value={pin}
                  onChange={(e) => {
                    const val = e.target.value.replace(/\D/g, "").slice(0, 6);
                    setPin(val);
                  }}
                  placeholder={t("pinPlaceholder")}
                  maxLength={6}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("hourlyRate")}</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={hourlyRate}
                  onChange={(e) => setHourlyRate(e.target.value)}
                  placeholder={t("ratePlaceholder")}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
                />
              </div>
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
                disabled={createEmployee.isPending || !name.trim() || !email.trim() || !locationId}
                className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50"
              >
                {createEmployee.isPending ? tc("creating") : t("addEmployee")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
