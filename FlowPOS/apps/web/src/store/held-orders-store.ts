"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CartItem } from "./cart-store";

export interface HeldOrder {
  id: string;
  items: CartItem[];
  heldAt: string; // ISO timestamp
  label?: string; // e.g. "Table #3" or custom note
}

interface HeldOrdersState {
  orders: HeldOrder[];
  holdOrder: (items: CartItem[], label?: string) => string; // returns id
  recallOrder: (id: string) => CartItem[] | null;
  removeOrder: (id: string) => void;
}

export const useHeldOrdersStore = create<HeldOrdersState>()(
  persist(
    (set, get) => ({
      orders: [],

      holdOrder: (items, label) => {
        const id = crypto.randomUUID();
        set((state) => ({
          orders: [
            ...state.orders,
            { id, items, heldAt: new Date().toISOString(), label },
          ],
        }));
        return id;
      },

      recallOrder: (id) => {
        const order = get().orders.find((o) => o.id === id);
        if (!order) return null;
        set((state) => ({
          orders: state.orders.filter((o) => o.id !== id),
        }));
        return order.items;
      },

      removeOrder: (id) =>
        set((state) => ({
          orders: state.orders.filter((o) => o.id !== id),
        })),
    }),
    { name: "held-orders" }
  )
);
