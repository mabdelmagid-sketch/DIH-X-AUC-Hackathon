"use client";

import { useState, useMemo } from "react";
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
import { trpc } from "@/lib/trpc";

export default function POSPage() {
  const router = useRouter();
  const t = useTranslations("pos");
  const [activeCategory, setActiveCategory] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [showHeld, setShowHeld] = useState(false);

  const items = useCartStore((s) => s.items);
  const addItem = useCartStore((s) => s.addItem);
  const clearCart = useCartStore((s) => s.clearCart);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const heldOrders = useHeldOrdersStore((s) => s.orders);
  const holdOrder = useHeldOrdersStore((s) => s.holdOrder);
  const recallOrder = useHeldOrdersStore((s) => s.recallOrder);
  const removeHeldOrder = useHeldOrdersStore((s) => s.removeOrder);

  // Fetch real products and categories from backend
  const { data: productsData, isLoading: productsLoading } = trpc.products.list.useQuery(
    { isActive: true, limit: 100 },
  );
  const { data: categoriesData } = trpc.categories.list.useQuery();

  // Build category tabs from real data
  const categories = useMemo(() => {
    if (!categoriesData) return ["All"];
    const names = categoriesData.map((c: { name: string }) => c.name);
    return ["All", ...names];
  }, [categoriesData]);

  // Map backend products to Product type
  const products: Product[] = useMemo(() => {
    if (!productsData?.products) return [];
    return productsData.products.map((p: {
      id: string;
      name: string;
      price: number;
      image?: string | null;
      category?: { name: string } | null;
    }) => ({
      id: p.id,
      name: p.name,
      price: p.price,
      category: p.category?.name ?? "Uncategorized",
      image: p.image ?? undefined,
    }));
  }, [productsData]);

  // Filter products by category and search
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
