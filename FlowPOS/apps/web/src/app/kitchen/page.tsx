"use client";

import { useState, useMemo, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { KDSHeader } from "@/components/kds/kds-header";
import {
  OrderCard,
  type KDSOrder,
} from "@/components/kds/order-card";
import { useAuthStore } from "@/store/auth-store";
import { trpc } from "@/lib/trpc";

const STATUSES = ["All", "New", "In Progress", "Ready"];

export default function KitchenPage() {
  const router = useRouter();
  const t = useTranslations("kitchen");
  const [activeStatus, setActiveStatus] = useState("All");
  const [soundEnabled, setSoundEnabled] = useState(true);
  const user = useAuthStore((s) => s.user);
  const locationId = user?.locationId;

  // Fetch KDS orders from backend
  const {
    data: ordersData,
    refetch,
    isLoading,
  } = trpc.orders.getForKDS.useQuery(
    { locationId: locationId! },
    {
      enabled: !!locationId,
      refetchInterval: 10_000, // poll every 10 seconds
    }
  );

  // Mutations for status updates
  const updateStatus = trpc.orders.updateStatus.useMutation({
    onSuccess: () => refetch(),
  });

  // Map backend orders → KDSOrder
  const orders: KDSOrder[] = useMemo(() => {
    if (!ordersData) return [];
    return ordersData.map((o: Record<string, unknown>) => {
      const table = o.table as { name?: string } | null;
      const items = (o.items as Array<Record<string, unknown>>) ?? [];
      const createdAt = new Date(o.created_at as string);
      const elapsedMs = Date.now() - createdAt.getTime();
      const elapsedMinutes = elapsedMs / 60_000;

      // Map DB status → KDS status
      const dbStatus = o.status as string;
      let status: "new" | "in_progress" | "ready";
      if (dbStatus === "OPEN") status = "new";
      else if (dbStatus === "IN_PROGRESS") status = "in_progress";
      else if (dbStatus === "READY") status = "ready";
      else status = "new";

      return {
        id: o.id as string,
        orderNumber: String(o.order_number ?? ""),
        status,
        elapsedMinutes,
        table: table?.name ?? undefined,
        type: (o.type as string) === "TAKEOUT" ? "Takeaway" : (o.type as string) === "DELIVERY" ? "Delivery" : undefined,
        items: items.map((item) => {
          const modifiers = (item.modifiers as Array<{ name: string }>) ?? [];
          return {
            name: item.name as string,
            quantity: item.quantity as number,
            modifier: modifiers.length > 0
              ? modifiers.map((m) => m.name).join(", ")
              : (item.notes as string) || undefined,
          };
        }),
      };
    });
  }, [ordersData]);

  // Live timer: re-render every 15 seconds to update elapsed times
  const [, setTick] = useState(0);
  const tickRef = useRef<ReturnType<typeof setInterval>>();
  useEffect(() => {
    tickRef.current = setInterval(() => setTick((t) => t + 1), 15_000);
    return () => clearInterval(tickRef.current);
  }, []);

  const filteredOrders = useMemo(() => {
    return orders.filter((order) => {
      if (activeStatus === "All") return true;
      if (activeStatus === "New") return order.status === "new";
      if (activeStatus === "In Progress") return order.status === "in_progress";
      if (activeStatus === "Ready") return order.status === "ready";
      return true;
    });
  }, [orders, activeStatus]);

  const handleBump = (id: string) => {
    updateStatus.mutate({ id, status: "READY" });
  };

  const handleStart = (id: string) => {
    updateStatus.mutate({ id, status: "IN_PROGRESS" });
  };

  if (!locationId) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--background)]">
        <div className="flex flex-col items-center gap-3 text-[var(--muted-foreground)]">
          <span className="material-symbols-sharp" style={{ fontSize: 48 }}>error_outline</span>
          <span className="font-brand text-lg">{t("noLocation")}</span>
          <span className="font-body text-sm">{t("noLocationMessage")}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-[var(--background)]">
      <KDSHeader
        statuses={STATUSES}
        activeStatus={activeStatus}
        onStatusChange={setActiveStatus}
        soundEnabled={soundEnabled}
        onToggleSound={() => setSoundEnabled(!soundEnabled)}
        orderCount={orders.length}
        onBack={() => router.push("/dashboard")}
      />

      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">{t("loadingOrders")}</span>
            </div>
          </div>
        ) : filteredOrders.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="flex flex-col items-center gap-3 text-[var(--muted-foreground)]">
              <span className="material-symbols-sharp" style={{ fontSize: 48 }}>restaurant</span>
              <span className="font-brand text-lg">{t("noOrders")}</span>
              <span className="font-body text-sm">{t("noOrdersMessage")}</span>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {filteredOrders.map((order) => (
              <OrderCard
                key={order.id}
                order={order}
                onBump={handleBump}
                onStart={handleStart}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
