"use client";

import { create } from "zustand";

export interface CartItem {
  id: string;
  name: string;
  price: number; // in cents
  quantity: number;
  image?: string;
}

export interface CartCustomer {
  id: string;
  name: string;
  phone?: string | null;
  loyaltyPoints?: number | null;
}

interface CartState {
  items: CartItem[];
  customer: CartCustomer | null;
  addItem: (item: Omit<CartItem, "quantity">) => void;
  removeItem: (id: string) => void;
  updateQuantity: (id: string, quantity: number) => void;
  setCustomer: (customer: CartCustomer | null) => void;
  clearCart: () => void;
  subtotal: () => number;
  tax: () => number;
  total: () => number;
  itemCount: () => number;
}

export const useCartStore = create<CartState>((set, get) => ({
  items: [],
  customer: null,

  addItem: (item) =>
    set((state) => {
      const existing = state.items.find((i) => i.id === item.id);
      if (existing) {
        return {
          items: state.items.map((i) =>
            i.id === item.id ? { ...i, quantity: i.quantity + 1 } : i
          ),
        };
      }
      return { items: [...state.items, { ...item, quantity: 1 }] };
    }),

  removeItem: (id) =>
    set((state) => ({
      items: state.items.filter((i) => i.id !== id),
    })),

  updateQuantity: (id, quantity) =>
    set((state) => {
      if (quantity <= 0) {
        return { items: state.items.filter((i) => i.id !== id) };
      }
      return {
        items: state.items.map((i) =>
          i.id === id ? { ...i, quantity } : i
        ),
      };
    }),

  setCustomer: (customer) => set({ customer }),

  clearCart: () => set({ items: [], customer: null }),

  subtotal: () =>
    get().items.reduce((sum, item) => sum + item.price * item.quantity, 0),

  tax: () => Math.round(get().subtotal() * 0.05),

  total: () => get().subtotal() + get().tax(),

  itemCount: () =>
    get().items.reduce((count, item) => count + item.quantity, 0),
}));
