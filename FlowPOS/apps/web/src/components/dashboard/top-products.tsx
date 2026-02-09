interface TopProduct {
  rank: number;
  name: string;
  revenue: string;
}

interface TopProductsProps {
  products: TopProduct[];
}

export function TopProducts({ products }: TopProductsProps) {
  return (
    <div className="flex h-full w-[340px] flex-col rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
      <div className="border-b border-[var(--border)] px-6 py-4">
        <span className="font-brand text-base font-semibold text-[var(--foreground)]">
          Top Products
        </span>
      </div>
      <div className="flex flex-1 flex-col py-2">
        {products.map((product) => (
          <div
            key={product.rank}
            className="flex items-center justify-between px-6 py-2.5"
          >
            <span className="font-body text-sm text-[var(--foreground)]">
              {product.rank}. {product.name}
            </span>
            <span className="font-brand text-sm font-semibold text-[var(--foreground)]">
              {product.revenue}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
