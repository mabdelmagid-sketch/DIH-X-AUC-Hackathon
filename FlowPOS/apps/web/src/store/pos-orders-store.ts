import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface POSOrder {
  id: string;
  code: string;
  status: string;
  type: string;
  total_amount: number;
  items_amount: number;
  discount_amount: number;
  payment_method: string;
  customer_name: string | null;
  channel: string | null;
  place_name: string | null;
  created: number;
  items: { title: string; quantity: number; price: number }[];
}

interface POSOrdersState {
  orders: POSOrder[];
  addOrder: (order: POSOrder) => void;
  clearOrders: () => void;
}

let orderCounter = 1;

export const usePOSOrdersStore = create<POSOrdersState>()(
  persist(
    (set) => ({
      orders: [],
      addOrder: (order) =>
        set((state) => ({ orders: [order, ...state.orders] })),
      clearOrders: () => set({ orders: [] }),
    }),
    { name: "pos-orders" }
  )
);

export function generateOrderCode(): string {
  const now = new Date();
  const num = orderCounter++;
  return `POS-${now.getHours().toString().padStart(2, "0")}${now.getMinutes().toString().padStart(2, "0")}-${num.toString().padStart(3, "0")}`;
}
