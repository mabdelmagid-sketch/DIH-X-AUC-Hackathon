"use client";

import { useState, useEffect, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn, formatCurrency } from "@/lib/utils";
import { getPlaces, getDataProducts } from "@/lib/forecasting-api";

export default function ProductsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const t = useTranslations("products");
  const tc = useTranslations("common");

  // Restaurant / product state (same pattern as POS page)
  const [places, setPlaces] = useState<{ id: number; title: string; order_count: number }[]>([]);
  const [placesLoading, setPlacesLoading] = useState(true);
  const [placeId, setPlaceId] = useState<number | null>(null);
  const [dataProducts, setDataProducts] = useState<
    { id: number; title: string; price: number; image: string | null; order_count: number }[]
  >([]);
  const [productsLoading, setProductsLoading] = useState(false);

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

  const products = useMemo(() => {
    if (!dataProducts.length) return [];
    const mapped = dataProducts.map((p) => ({
      id: p.id,
      name: p.title,
      price: Math.round((p.price ?? 0) * 100),
      image: p.image,
      orderCount: p.order_count,
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter((p) => p.name.toLowerCase().includes(q));
  }, [dataProducts, searchQuery]);

  const isLoading = placesLoading || productsLoading;

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${products.length} ${t("description")}`}
        />

        {/* Filters */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-sm">
            <Icon
              name="search"
              size={18}
              className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
            />
            <input
              type="text"
              placeholder={t("searchPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-10 w-full rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] ps-10 pe-4 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
            />
          </div>
          <select
            value={placeId ?? ""}
            onChange={(e) => setPlaceId(Number(e.target.value))}
            disabled={placesLoading}
            className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)] disabled:opacity-50"
          >
            {placesLoading ? (
              <option>Loading...</option>
            ) : (
              places.map((place) => (
                <option key={place.id} value={place.id}>
                  {place.title}
                </option>
              ))
            )}
          </select>
        </div>

        {/* Products Table */}
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">{t("loading")}</span>
            </div>
          </div>
        ) : products.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="inventory_2" size={40} />
              <span className="font-body text-sm">{t("noProducts")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("product")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("price")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">Popularity</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product, idx) => (
                  <tr
                    key={product.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                      idx < products.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        {product.image ? (
                          <img
                            src={product.image}
                            alt={product.name}
                            className="h-10 w-10 rounded-[var(--radius-m)] object-cover"
                          />
                        ) : (
                          <div className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-m)] bg-[var(--secondary)]">
                            <Icon name="fastfood" size={20} className="text-[var(--muted-foreground)]" />
                          </div>
                        )}
                        <span className="font-brand text-sm font-medium text-[var(--foreground)]">
                          {product.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {formatCurrency(product.price)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1 font-body text-sm text-[var(--muted-foreground)]">
                        <Icon name="shopping_bag" size={14} />
                        {product.orderCount} orders
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                        {tc("active")}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
