import { cn } from "@/lib/utils";

type OrderStatus = "Ready" | "Preparing" | "Completed";

interface RecentOrder {
  id: string;
  time: string;
  items: string;
  total: string;
  status: OrderStatus;
}

interface RecentOrdersProps {
  orders: RecentOrder[];
}

function StatusBadge({ status }: { status: OrderStatus }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-[var(--radius-pill)] border px-2.5 py-0.5 font-body text-xs font-medium",
        status === "Ready" &&
          "border-[var(--border)] bg-[var(--card)] text-[var(--color-success-foreground)]",
        status === "Preparing" &&
          "border-transparent bg-[var(--color-warning)] text-[var(--color-warning-foreground)]",
        status === "Completed" &&
          "border-[var(--border)] bg-[var(--card)] text-[var(--muted-foreground)]"
      )}
    >
      {status}
    </span>
  );
}

export function RecentOrders({ orders }: RecentOrdersProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="font-brand text-base font-semibold text-[var(--foreground)]">
          Recent Orders
        </span>
        <button className="font-brand text-sm text-[var(--foreground)] hover:underline">
          View All
        </button>
      </div>
      <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--border)] bg-[var(--card)]">
              <th className="px-3 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">
                Order
              </th>
              <th className="px-3 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">
                Time
              </th>
              <th className="px-3 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">
                Items
              </th>
              <th className="px-3 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">
                Total
              </th>
              <th className="px-3 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">
                Status
              </th>
              <th className="px-3 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order, idx) => (
              <tr
                key={order.id}
                className={cn(
                  "bg-[var(--card)]",
                  idx < orders.length - 1 && "border-b border-[var(--border)]"
                )}
              >
                <td className="px-3 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                  #{order.id}
                </td>
                <td className="px-3 py-3 font-body text-sm text-[var(--foreground)]">
                  {order.time}
                </td>
                <td className="px-3 py-3 font-body text-sm text-[var(--foreground)]">
                  {order.items}
                </td>
                <td className="px-3 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                  {order.total}
                </td>
                <td className="px-3 py-3">
                  <StatusBadge status={order.status} />
                </td>
                <td className="px-3 py-3">
                  <button className="font-brand text-sm text-[var(--foreground)] hover:underline">
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
