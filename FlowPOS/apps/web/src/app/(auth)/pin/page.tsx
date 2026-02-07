"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { Avatar, Button, Input } from "@/components/ui";
import { useAuthStore, type PinVerifyResult } from "@/store/auth-store";
import { trpc } from "@/lib/trpc";

const PIN_LENGTH = 6;

type Phase = "store" | "pin";

export default function PinEntryPage() {
  const router = useRouter();
  const { loginWithPin, isAuthenticated, isLoading: authLoading, storeConfig } = useAuthStore();
  const t = useTranslations("auth");
  const tc = useTranslations("common");

  const [phase, setPhase] = useState<Phase>(storeConfig ? "pin" : "store");
  const [storeCode, setStoreCode] = useState(storeConfig?.code ?? "");
  const [storeName, setStoreName] = useState(storeConfig?.name ?? "");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // tRPC mutations
  const getStoreByCode = trpc.auth.getStoreByCode.useQuery(
    { code: storeCode },
    { enabled: false }
  );

  const verifyStorePin = trpc.auth.verifyStorePin.useMutation();

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      router.replace("/pos");
    }
  }, [isAuthenticated, authLoading, router]);

  // Phase 1: Validate store code
  async function handleStoreSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!storeCode.trim()) return;

    setError(null);
    setIsLoading(true);

    try {
      const result = await getStoreByCode.refetch();
      const store = result.data;

      if (!store) {
        setError(t("storeNotFound"));
        setIsLoading(false);
        return;
      }

      setStoreName(store.name);
      useAuthStore.getState().setStoreConfig({
        id: store.id,
        name: store.name,
        code: storeCode,
        logo: store.logo ?? undefined,
      });
      setPhase("pin");
    } catch {
      setError(t("storeCheckFailed"));
    } finally {
      setIsLoading(false);
    }
  }

  // Phase 2: Handle PIN digit entry
  const handleDigit = useCallback(
    (digit: string) => {
      if (pin.length >= PIN_LENGTH || isLoading) return;
      const newPin = pin + digit;
      setPin(newPin);

      // Auto-submit when PIN is complete
      if (newPin.length === PIN_LENGTH) {
        submitPin(newPin);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pin, isLoading]
  );

  async function submitPin(enteredPin: string) {
    setError(null);
    setIsLoading(true);

    try {
      const result = await verifyStorePin.mutateAsync({
        storeCode,
        pin: enteredPin,
      });

      // Pass the result to loginWithPin - it matches PinVerifyResult shape
      loginWithPin(storeCode, enteredPin, result as unknown as PinVerifyResult);
      // Redirect happens via useEffect above
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t("invalidPin");
      setError(message);
      setPin("");
      setIsLoading(false);
    }
  }

  const handleDelete = useCallback(() => {
    setError(null);
    setPin((prev) => prev.slice(0, -1));
  }, []);

  function handleSwitchStore() {
    useAuthStore.getState().clearStoreConfig();
    setPhase("store");
    setStoreCode("");
    setStoreName("");
    setPin("");
    setError(null);
  }

  // Phase 1: Store code entry
  if (phase === "store") {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--background)] p-6">
        <div className="flex flex-col items-center w-full max-w-[380px]">
          <h1 className="text-2xl font-brand font-bold text-[var(--primary)]">
            {tc("flowPos")}
          </h1>
          <p className="mt-2 text-sm font-body text-[var(--muted-foreground)]">
            {t("storeCodePrompt")}
          </p>

          {error && (
            <div className="mt-4 w-full rounded-[var(--radius-m)] border border-[var(--color-error)] bg-[var(--color-error)] px-4 py-3">
              <p className="text-sm font-body text-[var(--color-error-foreground)]">
                {error}
              </p>
            </div>
          )}

          <form onSubmit={handleStoreSubmit} className="mt-6 flex w-full flex-col gap-4">
            <Input
              label={t("storeCode")}
              type="text"
              placeholder={t("storeCodePlaceholder")}
              value={storeCode}
              onChange={(e) => setStoreCode(e.target.value.toLowerCase().replace(/\s+/g, "-"))}
              required
            />
            <Button type="submit" variant="primary" disabled={isLoading || !storeCode.trim()}>
              {isLoading ? t("lookingUp") : tc("continue")}
            </Button>
          </form>

          <Link
            href="/login"
            className="mt-6 text-sm font-body text-[var(--foreground)] hover:underline"
          >
            {t("signInWithEmail")}
          </Link>
        </div>
      </div>
    );
  }

  // Phase 2: PIN entry
  return (
    <div className="flex h-full items-center justify-center bg-[var(--background)] p-6">
      <div className="flex flex-col items-center w-full max-w-[320px]">
        {/* Store Avatar */}
        <Avatar name={storeName || "Store"} size={64} />

        {/* Branding */}
        <h1 className="mt-4 text-xl font-brand font-bold text-[var(--foreground)]">
          {storeName || tc("flowPos")}
        </h1>
        <p className="mt-1 text-sm font-body text-[var(--muted-foreground)]">
          {t("enterPin")}
        </p>

        {/* Error Message */}
        {error && (
          <div className="mt-4 w-full rounded-[var(--radius-m)] border border-[var(--color-error)] bg-[var(--color-error)] px-4 py-3">
            <p className="text-sm font-body text-center text-[var(--color-error-foreground)]">
              {error}
            </p>
          </div>
        )}

        {/* PIN Dots */}
        <div className="flex items-center gap-3 mt-8">
          {Array.from({ length: PIN_LENGTH }).map((_, i) => (
            <div
              key={i}
              className={cn(
                "w-3 h-3 rounded-full transition-colors",
                i < pin.length
                  ? "bg-[var(--primary)]"
                  : "bg-[var(--border)]"
              )}
            />
          ))}
        </div>

        {/* Numeric Keypad */}
        <div className="grid grid-cols-3 gap-4 mt-10 w-full max-w-[240px]">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((digit) => (
            <button
              key={digit}
              onClick={() => handleDigit(digit)}
              disabled={isLoading}
              className={cn(
                "flex items-center justify-center w-16 h-16 mx-auto",
                "rounded-full bg-[var(--secondary)] text-xl font-brand font-medium",
                "text-[var(--foreground)] cursor-pointer",
                "hover:bg-[var(--border)] active:scale-95 transition-all",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {digit}
            </button>
          ))}

          {/* Delete */}
          <button
            onClick={handleDelete}
            disabled={isLoading || pin.length === 0}
            className={cn(
              "flex items-center justify-center w-16 h-16 mx-auto",
              "rounded-full bg-[#FF5C33] text-white text-sm font-brand font-medium",
              "cursor-pointer hover:opacity-90 active:scale-95 transition-all",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            {t("del")}
          </button>

          {/* Zero */}
          <button
            onClick={() => handleDigit("0")}
            disabled={isLoading}
            className={cn(
              "flex items-center justify-center w-16 h-16 mx-auto",
              "rounded-full bg-[var(--secondary)] text-xl font-brand font-medium",
              "text-[var(--foreground)] cursor-pointer",
              "hover:bg-[var(--border)] active:scale-95 transition-all",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            0
          </button>

          {/* Enter placeholder */}
          <div className="w-16 h-16 mx-auto rounded-full bg-[var(--secondary)] opacity-30" />
        </div>

        {/* Actions */}
        <div className="flex items-center gap-4 mt-8">
          <button
            onClick={handleSwitchStore}
            className="text-sm font-body text-[var(--muted-foreground)] hover:underline"
          >
            {t("switchStore")}
          </button>
          <span className="text-[var(--border)]">|</span>
          <Link
            href="/login"
            className="text-sm font-body text-[var(--foreground)] hover:underline"
          >
            {t("emailLogin")}
          </Link>
        </div>
      </div>
    </div>
  );
}
