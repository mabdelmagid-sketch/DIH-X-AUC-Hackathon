"use client";

import { useState, useEffect } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { trpc } from "@/lib/trpc";
import { cn } from "@/lib/utils";
import { usePrinterStore, type PrinterType, type PaperWidth } from "@/store/printer-store";

/* ─── Inline Edit Row ──────────────────────────────────── */

function EditableRow({
  label,
  value,
  onSave,
  type = "text",
  isLast = false,
}: {
  label: string;
  value: string;
  onSave: (val: string) => void;
  type?: "text" | "number";
  isLast?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const handleSave = () => {
    onSave(draft);
    setEditing(false);
  };

  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 py-3",
        !isLast && "border-b border-[var(--border)]"
      )}
    >
      <div className="flex flex-col gap-0.5 min-w-0 flex-1">
        <span className="font-body text-xs text-[var(--muted-foreground)]">{label}</span>
        {editing ? (
          <div className="flex items-center gap-2">
            <input
              type={type}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSave();
                if (e.key === "Escape") { setDraft(value); setEditing(false); }
              }}
              className="h-8 flex-1 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-2 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
            />
            <button
              onClick={handleSave}
              className="rounded-full p-1 text-[var(--primary)] hover:bg-green-50 dark:hover:bg-green-900/20"
            >
              <Icon name="check" size={16} />
            </button>
            <button
              onClick={() => { setDraft(value); setEditing(false); }}
              className="rounded-full p-1 text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
            >
              <Icon name="close" size={16} />
            </button>
          </div>
        ) : (
          <span className="font-body text-sm text-[var(--foreground)] truncate">
            {value || "—"}
          </span>
        )}
      </div>
      {!editing && (
        <button
          onClick={() => setEditing(true)}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] hover:bg-[var(--accent)]"
        >
          <Icon name="edit" size={14} />
        </button>
      )}
    </div>
  );
}

/* ─── Toggle Row ───────────────────────────────────────── */

function ToggleRow({
  label,
  description,
  enabled,
  onChange,
  isLast = false,
}: {
  label: string;
  description: string;
  enabled: boolean;
  onChange: (val: boolean) => void;
  isLast?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 py-3",
        !isLast && "border-b border-[var(--border)]"
      )}
    >
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="font-brand text-sm font-medium text-[var(--foreground)]">{label}</span>
        <span className="font-body text-xs text-[var(--muted-foreground)]">{description}</span>
      </div>
      <button
        onClick={() => onChange(!enabled)}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-[var(--radius-pill)] transition-colors",
          enabled ? "bg-[var(--primary)]" : "bg-[var(--input)]"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform",
            enabled ? "start-[22px]" : "start-0.5"
          )}
        />
      </button>
    </div>
  );
}

/* ─── Select Row ───────────────────────────────────────── */

function SelectRow({
  label,
  value,
  options,
  onSave,
  isLast = false,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onSave: (val: string) => void;
  isLast?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 py-3",
        !isLast && "border-b border-[var(--border)]"
      )}
    >
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="font-body text-xs text-[var(--muted-foreground)]">{label}</span>
      </div>
      <select
        value={value}
        onChange={(e) => onSave(e.target.value)}
        className="h-8 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-2 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </div>
  );
}

/* ─── Section Card ─────────────────────────────────────── */

function SettingsSection({
  icon,
  title,
  description,
  children,
  variant = "default",
}: {
  icon: string;
  title: string;
  description: string;
  children: React.ReactNode;
  variant?: "default" | "danger";
}) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-m)] border bg-[var(--card)]",
        variant === "danger" ? "border-red-300 dark:border-red-800/50" : "border-[var(--border)]"
      )}
    >
      <div className="flex items-center gap-3 border-b border-[var(--border)] px-6 py-4">
        <div
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-[var(--radius-m)]",
            variant === "danger" ? "bg-red-100 dark:bg-red-900/30" : "bg-[var(--secondary)]"
          )}
        >
          <Icon
            name={icon}
            size={18}
            className={variant === "danger" ? "text-red-600 dark:text-red-400" : "text-[var(--muted-foreground)]"}
          />
        </div>
        <div className="flex flex-col gap-0.5">
          <h2
            className={cn(
              "font-brand text-sm font-semibold",
              variant === "danger" ? "text-red-600 dark:text-red-400" : "text-[var(--foreground)]"
            )}
          >
            {title}
          </h2>
          <p className="font-body text-xs text-[var(--muted-foreground)]">{description}</p>
        </div>
      </div>
      <div className="px-6">{children}</div>
    </div>
  );
}

/* ─── Currency Options ─────────────────────────────────── */

const CURRENCIES = [
  { value: "USD", label: "USD ($)" },
  { value: "EUR", label: "EUR (€)" },
  { value: "GBP", label: "GBP (£)" },
  { value: "SAR", label: "SAR (﷼)" },
  { value: "AED", label: "AED (د.إ)" },
  { value: "JOD", label: "JOD (د.ا)" },
  { value: "EGP", label: "EGP (ج.م)" },
  { value: "TRY", label: "TRY (₺)" },
];

/* ─── Printer Section ─────────────────────────────────── */

function PrinterSection() {
  const t = useTranslations("settings");
  const {
    printerType,
    paperWidth,
    autoPrintOnCheckout,
    autoPrintKitchen,
    networkPrinterIp,
    networkPrinterPort,
    isConnected,
    setPrinterType,
    setPaperWidth,
    setAutoPrintOnCheckout,
    setAutoPrintKitchen,
    setNetworkPrinterIp,
    setNetworkPrinterPort,
    connectUsb,
    connectBluetooth,
    disconnect,
    printTestPage,
  } = usePrinterStore();

  const [connecting, setConnecting] = useState(false);
  const [testing, setTesting] = useState(false);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      if (printerType === "usb") await connectUsb();
      else if (printerType === "bluetooth") await connectBluetooth();
    } finally {
      setConnecting(false);
    }
  };

  const handleTestPrint = async () => {
    setTesting(true);
    try {
      await printTestPage();
    } finally {
      setTesting(false);
    }
  };

  const needsConnection = printerType === "usb" || printerType === "bluetooth";

  const printerTypes: { value: PrinterType; label: string }[] = [
    { value: "browser", label: t("browserPrint") },
    { value: "usb", label: t("usbThermal") },
    { value: "bluetooth", label: t("bluetooth") },
    { value: "network", label: t("networkIp") },
  ];

  const paperWidths: { value: PaperWidth; label: string }[] = [
    { value: "80mm", label: t("paperStandard") },
    { value: "58mm", label: t("paperCompact") },
  ];

  return (
    <SettingsSection
      icon="print"
      title={t("printer")}
      description={t("printerDesc")}
    >
      <SelectRow
        label={t("printerType")}
        value={printerType}
        options={printerTypes}
        onSave={(val) => setPrinterType(val as PrinterType)}
      />
      <SelectRow
        label={t("paperWidth")}
        value={paperWidth}
        options={paperWidths}
        onSave={(val) => setPaperWidth(val as PaperWidth)}
      />

      {printerType === "network" && (
        <>
          <EditableRow
            label={t("printerIp")}
            value={networkPrinterIp}
            onSave={setNetworkPrinterIp}
          />
          <EditableRow
            label={t("printerPort")}
            value={String(networkPrinterPort)}
            type="number"
            onSave={(val) => setNetworkPrinterPort(Number(val) || 9100)}
          />
        </>
      )}

      <ToggleRow
        label={t("autoPrintCheckout")}
        description={t("autoPrintCheckoutDesc")}
        enabled={autoPrintOnCheckout}
        onChange={setAutoPrintOnCheckout}
      />
      <ToggleRow
        label={t("autoPrintKitchen")}
        description={t("autoPrintKitchenDesc")}
        enabled={autoPrintKitchen}
        onChange={setAutoPrintKitchen}
        isLast={!needsConnection && printerType !== "network"}
      />

      {/* Connection + Test buttons */}
      <div className="flex items-center gap-3 py-4">
        {needsConnection && (
          <button
            onClick={isConnected ? disconnect : handleConnect}
            disabled={connecting}
            className={cn(
              "flex items-center gap-2 rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm font-medium transition-colors",
              isConnected
                ? "border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] hover:bg-[var(--accent)]"
                : "bg-[var(--primary)] text-white hover:bg-[var(--primary)]/90",
              connecting && "opacity-50"
            )}
          >
            <Icon
              name={isConnected ? "link_off" : connecting ? "sync" : "link"}
              size={16}
              className={cn(connecting && "animate-spin")}
            />
            {isConnected ? t("disconnect") : connecting ? t("connecting") : t("connect")}
          </button>
        )}

        {isConnected && needsConnection && (
          <span className="flex items-center gap-1.5 font-body text-xs text-green-600 dark:text-green-400">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            {t("connected")}
          </span>
        )}

        <button
          onClick={handleTestPrint}
          disabled={testing || (needsConnection && !isConnected)}
          className="flex items-center gap-2 rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--background)] px-4 py-2 font-brand text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--accent)] disabled:opacity-50"
        >
          <Icon name="print" size={16} />
          {testing ? t("printing") : t("testPrint")}
        </button>
      </div>
    </SettingsSection>
  );
}

/* ─── Main Page ────────────────────────────────────────── */

export default function SettingsPage() {
  const t = useTranslations("settings");
  const tc = useTranslations("common");
  const utils = trpc.useUtils();

  const { data: org, isLoading: orgLoading } = trpc.organization.get.useQuery();
  const { data: settings, isLoading: settingsLoading } = trpc.organization.getSettings.useQuery();

  const updateOrg = trpc.organization.update.useMutation({
    onSuccess: () => utils.organization.get.invalidate(),
  });
  const updateSettings = trpc.organization.updateSettings.useMutation({
    onSuccess: () => utils.organization.getSettings.invalidate(),
  });

  const isLoading = orgLoading || settingsLoading;

  if (isLoading) {
    return (
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <PageHeader title={t("title")} description={t("description")} />
          <div className="flex items-center justify-center py-20">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
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
          description={t("description")}
        />

        {/* General */}
        <SettingsSection
          icon="store"
          title={t("general")}
          description={t("generalDesc")}
        >
          <EditableRow
            label={t("businessName")}
            value={org?.name ?? ""}
            onSave={(val) => updateOrg.mutate({ name: val })}
          />
          <SelectRow
            label={t("currency")}
            value={settings?.currency ?? "USD"}
            options={CURRENCIES}
            onSave={(val) => updateSettings.mutate({ currency: val })}
          />
          <EditableRow
            label={t("taxRate")}
            value={String((settings?.tax_rate ?? 0) / 100)}
            type="number"
            onSave={(val) => updateSettings.mutate({ taxRate: Math.round(Number(val) * 100) })}
            isLast
          />
        </SettingsSection>

        {/* POS */}
        <SettingsSection
          icon="point_of_sale"
          title={t("posSettings")}
          description={t("posDesc")}
        >
          <ToggleRow
            label={t("taxInclusive")}
            description={t("taxInclusiveDesc")}
            enabled={settings?.tax_inclusive ?? false}
            onChange={(val) => updateSettings.mutate({ taxInclusive: val })}
          />
          <ToggleRow
            label={t("requirePin")}
            description={t("requirePinDesc")}
            enabled={settings?.require_pin ?? false}
            onChange={(val) => updateSettings.mutate({ requirePin: val })}
          />
          <ToggleRow
            label={t("allowNegativeStock")}
            description={t("allowNegativeStockDesc")}
            enabled={settings?.allow_negative ?? false}
            onChange={(val) => updateSettings.mutate({ allowNegative: val })}
            isLast
          />
        </SettingsSection>

        {/* Receipt */}
        <SettingsSection
          icon="receipt_long"
          title={t("receipt")}
          description={t("receiptDesc")}
        >
          <EditableRow
            label={t("receiptHeader")}
            value={settings?.receipt_header ?? ""}
            onSave={(val) => updateSettings.mutate({ receiptHeader: val || null })}
          />
          <EditableRow
            label={t("receiptFooter")}
            value={settings?.receipt_footer ?? ""}
            onSave={(val) => updateSettings.mutate({ receiptFooter: val || null })}
          />
          <ToggleRow
            label={t("showLogo")}
            description={t("showLogoDesc")}
            enabled={settings?.show_logo ?? true}
            onChange={(val) => updateSettings.mutate({ showLogo: val })}
            isLast
          />
        </SettingsSection>

        {/* Printer */}
        <PrinterSection />

        {/* Danger Zone */}
        <SettingsSection
          icon="warning"
          title={t("dangerZone")}
          description={t("dangerZoneDesc")}
          variant="danger"
        >
          <div className="flex items-center justify-between gap-4 py-4">
            <div className="flex flex-col gap-0.5 min-w-0">
              <span className="font-brand text-sm font-medium text-[var(--foreground)]">
                {t("deleteOrg")}
              </span>
              <span className="font-body text-xs text-[var(--muted-foreground)]">
                {t("deleteOrgDescription")}
              </span>
            </div>
            <button
              disabled
              className="shrink-0 rounded-[var(--radius-m)] border border-red-300 bg-red-50 px-4 py-2 font-body text-sm font-medium text-red-600 opacity-50 cursor-not-allowed dark:border-red-800/50 dark:bg-red-900/20 dark:text-red-400"
            >
              {tc("save")}
            </button>
          </div>
        </SettingsSection>
      </div>
    </DashboardLayout>
  );
}
