"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { POSHeader } from "@/components/pos/pos-header";
import { CategoryTabs } from "@/components/pos/category-tabs";
import { ProductGrid, type Product } from "@/components/pos/product-grid";
import { CartPanel, CartBottomBar } from "@/components/pos/cart-panel";
import { HeldOrdersDrawer } from "@/components/pos/held-orders-drawer";
import { useCartStore } from "@/store/cart-store";
import { useHeldOrdersStore } from "@/store/held-orders-store";
import { useAuthStore } from "@/store/auth-store";
import { getPlaces, getDataProducts } from "@/lib/forecasting-api";

export default function POSPage() {
  const router = useRouter();
  const t = useTranslations("pos");
  const [activeCategory, setActiveCategory] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [showHeld, setShowHeld] = useState(false);

  // Restaurant / product state
  const [places, setPlaces] = useState<{ id: number; title: string; order_count: number }[]>([]);
  const [placesLoading, setPlacesLoading] = useState(true);
  const [placeId, setPlaceId] = useState<number | null>(null);
  const [dataProducts, setDataProducts] = useState<
    { id: number; title: string; price: number; image: string | null; order_count: number }[]
  >([]);
  const [productsLoading, setProductsLoading] = useState(false);

  const items = useCartStore((s) => s.items);
  const addItem = useCartStore((s) => s.addItem);
  const clearCart = useCartStore((s) => s.clearCart);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const heldOrders = useHeldOrdersStore((s) => s.orders);
  const holdOrder = useHeldOrdersStore((s) => s.holdOrder);
  const recallOrder = useHeldOrdersStore((s) => s.recallOrder);
  const removeHeldOrder = useHeldOrdersStore((s) => s.removeOrder);

  // Fetch places on mount
  useEffect(() => {
    let cancelled = false;
    setPlacesLoading(true);
    getPlaces()
      .then((res) => {
        if (cancelled) return;
        setPlaces(res.places);
        if (res.places.length > 0) {
          setPlaceId(res.places[0].id);
        }
      })
      .catch((err) => {
        if (!cancelled) console.error("Failed to load places:", err);
      })
      .finally(() => {
        if (!cancelled) setPlacesLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  // Fetch products when placeId changes
  useEffect(() => {
    if (placeId == null) return;
    let cancelled = false;
    setProductsLoading(true);
    getDataProducts(placeId)
      .then((res) => {
        if (cancelled) return;
        setDataProducts(res.products);
      })
      .catch((err) => {
        if (!cancelled) console.error("Failed to load products:", err);
      })
      .finally(() => {
        if (!cancelled) setProductsLoading(false);
      });
    return () => { cancelled = true; };
  }, [placeId]);

  // Categories — dataset has no category names, so just "All"
  const categories = ["All"];

  // Map dataset products to POS Product type (price * 100 for cents)
  const products: Product[] = useMemo(() => {
    return dataProducts.map((p) => ({
      id: String(p.id),
      name: p.title,
      price: Math.round((p.price ?? 0) * 100),
      category: "All",
      image: p.image ?? undefined,
    }));
  }, [dataProducts]);

  // Filter products by search
  const filteredProducts = useMemo(() => {
    return products.filter((product) => {
      const matchesCategory =
        activeCategory === "All" || product.category === activeCategory;
      const matchesSearch = product.name
        .toLowerCase()
        .includes(searchQuery.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [products, activeCategory, searchQuery]);

  const handleProductClick = (product: Product) => {
    addItem({
      id: product.id,
      name: product.name,
      price: product.price,
      image: product.image,
    });
  };

  const handleHold = () => {
    if (items.length === 0) {
      // No items in cart — show held orders drawer instead
      if (heldOrders.length > 0) setShowHeld(true);
      return;
    }
    holdOrder(items);
    clearCart();
  };

  const handleRecall = (id: string) => {
    const recalledItems = recallOrder(id);
    if (recalledItems) {
      // If cart has items, hold them first
      if (items.length > 0) {
        holdOrder(items);
      }
      clearCart();
      recalledItems.forEach((item) => {
        for (let i = 0; i < item.quantity; i++) {
          addItem({ id: item.id, name: item.name, price: item.price, image: item.image });
        }
      });
    }
    setShowHeld(false);
  };

  const handleSignOut = () => {
    logout();
    router.replace("/login");
  };

  // Cashier info from auth
  const cashierName = user?.name ?? "Cashier";
  const cashierInitials = cashierName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="flex h-screen flex-col bg-[var(--background)]">
      {/* Header */}
      <POSHeader
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        cashierName={cashierName}
        cashierInitials={cashierInitials}
        onHold={handleHold}
        onClearCart={() => clearCart()}
        onViewHeld={() => setShowHeld(true)}
        onBackToDashboard={() => router.push("/dashboard")}
        onSignOut={handleSignOut}
        heldCount={heldOrders.length}
      />

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Products Panel */}
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-5">
          {/* Restaurant selector */}
          <div className="flex items-center gap-3">
            <label
              htmlFor="place-select"
              className="font-body text-sm font-medium text-[var(--foreground)]"
            >
              Restaurant:
            </label>
            <select
              id="place-select"
              className="rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-1.5 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              value={placeId ?? ""}
              onChange={(e) => setPlaceId(Number(e.target.value))}
              disabled={placesLoading}
            >
              {placesLoading ? (
                <option>Loading restaurants...</option>
              ) : places.length === 0 ? (
                <option>No restaurants found</option>
              ) : (
                places.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} ({p.order_count.toLocaleString()} orders)
                  </option>
                ))
              )}
            </select>
          </div>

          <CategoryTabs
            categories={categories}
            activeCategory={activeCategory}
            onChange={setActiveCategory}
          />

          {productsLoading ? (
            <div className="flex flex-1 items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
                <span className="font-body text-sm text-[var(--muted-foreground)]">{t("loadingProducts")}</span>
              </div>
            </div>
          ) : filteredProducts.length === 0 ? (
            <div className="flex flex-1 items-center justify-center">
              <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
                <span className="material-symbols-sharp" style={{ fontSize: 40 }}>inventory_2</span>
                <span className="font-body text-sm">{t("noProducts")}</span>
                <span className="font-body text-xs">{t("addProductsPrompt")}</span>
              </div>
            </div>
          ) : (
            <ProductGrid
              products={filteredProducts}
              onProductClick={handleProductClick}
            />
          )}
        </div>

        {/* Cart Panel - desktop only */}
        <div className="hidden lg:block">
          <CartPanel />
        </div>
      </div>

      {/* Cart Bottom Bar - tablet/mobile only */}
      <CartBottomBar />

      {/* Held Orders Drawer */}
      <HeldOrdersDrawer
        open={showHeld}
        onClose={() => setShowHeld(false)}
        orders={heldOrders}
        onRecall={handleRecall}
        onRemove={removeHeldOrder}
      />
    </div>
  );
}
