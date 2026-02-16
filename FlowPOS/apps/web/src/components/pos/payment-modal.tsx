"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Modal } from "@/components/ui";
import { Icon } from "@/components/ui";
import { formatCurrency } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

type PaymentMethod = "CASH" | "CARD" | "MOBILE" | "OTHER";

interface PaymentModalProps {
  open: boolean;
  onClose: () => void;
  orderId: string | null;
  total: number;
  onSuccess: () => void;
}

const PAYMENT_METHODS: { value: PaymentMethod; icon: string; labelKey: string }[] = [
  { value: "CASH", icon: "payments", labelKey: "cash" },
  { value: "CARD", icon: "credit_card", labelKey: "card" },
  { value: "MOBILE", icon: "smartphone", labelKey: "mobile" },
  { value: "OTHER", icon: "more_horiz", labelKey: "other" },
];

export function PaymentModal({ open, onClose, orderId, total, onSuccess }: PaymentModalProps) {
  const t = useTranslations("pos");
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod>("CASH");
  const [cashReceived, setCashReceived] = useState<string>("");
  const [isProcessing, setIsProcessing] = useState(false);

  const utils = trpc.useUtils();
  const checkoutMutation = trpc.orders.checkout.useMutation({
    onSuccess: () => {
      utils.orders.invalidate();
      onSuccess();
      handleClose();
    },
    onError: (error) => {
      alert(error.message);
      setIsProcessing(false);
    },
  });

  const handleClose = () => {
    setSelectedMethod("CASH");
    setCashReceived("");
    setIsProcessing(false);
    onClose();
  };

  const handlePayment = () => {
    if (!orderId) return;

    setIsProcessing(true);

    const paymentAmount = selectedMethod === "CASH" && cashReceived
      ? Math.round(parseFloat(cashReceived) * 100)
      : total;

    checkoutMutation.mutate({
      orderId,
      payments: [
        {
          method: selectedMethod,
          amount: Math.max(paymentAmount, total),
          tipAmount: 0,
        },
      ],
      status: "COMPLETED",
    });
  };

  const cashReceivedCents = cashReceived ? Math.round(parseFloat(cashReceived) * 100) : 0;
  const change = cashReceivedCents > total ? cashReceivedCents - total : 0;

  // Quick cash amounts
  const quickAmounts = [
    Math.ceil(total / 100) * 100,
    Math.ceil(total / 500) * 500,
    Math.ceil(total / 1000) * 1000,
    Math.ceil(total / 2000) * 2000,
  ].filter((v, i, a) => a.indexOf(v) === i && v >= total);

  return (
    <Modal open={open} onClose={handleClose} title={t("payment")} className="max-w-md">
      <div className="flex flex-col gap-4">
        {/* Total Display */}
        <div className="rounded-[var(--radius-m)] bg-[var(--accent)] p-4 text-center">
          <span className="font-body text-sm text-[var(--muted-foreground)]">{t("total")}</span>
          <div className="font-brand text-3xl font-bold text-[var(--foreground)]">
            {formatCurrency(total)}
          </div>
        </div>

        {/* Payment Methods */}
        <div className="grid grid-cols-4 gap-2">
          {PAYMENT_METHODS.map((method) => (
            <button
              key={method.value}
              onClick={() => setSelectedMethod(method.value)}
              className={`flex flex-col items-center gap-1 rounded-[var(--radius-m)] border p-3 transition-colors ${
                selectedMethod === method.value
                  ? "border-[var(--primary)] bg-[var(--primary)]/10 text-[var(--primary)]"
                  : "border-[var(--border)] text-[var(--muted-foreground)] hover:border-[var(--primary)]/50"
              }`}
            >
              <Icon name={method.icon} size={24} />
              <span className="font-body text-xs">{t(method.labelKey)}</span>
            </button>
          ))}
        </div>

        {/* Cash Input */}
        {selectedMethod === "CASH" && (
          <div className="flex flex-col gap-3">
            <div>
              <label className="font-body text-sm text-[var(--muted-foreground)]">
                {t("cashReceived")}
              </label>
              <input
                type="number"
                step="0.01"
                value={cashReceived}
                onChange={(e) => setCashReceived(e.target.value)}
                placeholder={formatCurrency(total)}
                className="mt-1 h-12 w-full rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-4 font-brand text-xl text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              />
            </div>

            {/* Quick amounts */}
            <div className="flex flex-wrap gap-2">
              {quickAmounts.slice(0, 4).map((amount) => (
                <button
                  key={amount}
                  onClick={() => setCashReceived((amount / 100).toFixed(2))}
                  className="rounded-[var(--radius-m)] border border-[var(--border)] px-3 py-1.5 font-body text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
                >
                  {formatCurrency(amount)}
                </button>
              ))}
            </div>

            {/* Change display */}
            {change > 0 && (
              <div className="rounded-[var(--radius-m)] bg-[var(--color-success)]/10 p-3 text-center">
                <span className="font-body text-sm text-[var(--color-success)]">{t("change")}</span>
                <div className="font-brand text-2xl font-bold text-[var(--color-success)]">
                  {formatCurrency(change)}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Pay Button */}
        <button
          onClick={handlePayment}
          disabled={isProcessing || (selectedMethod === "CASH" && cashReceivedCents > 0 && cashReceivedCents < total)}
          className="flex h-14 w-full items-center justify-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] font-brand text-lg font-semibold text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isProcessing ? (
            <>
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
              {t("processing")}
            </>
          ) : (
            <>
              <Icon name="check_circle" size={24} />
              {t("completePayment")}
            </>
          )}
        </button>
      </div>
    </Modal>
  );
}
