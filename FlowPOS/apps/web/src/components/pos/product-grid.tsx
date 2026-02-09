"use client";

import { ProductCard } from "./product-card";
import { cn } from "@/lib/utils";

export interface Product {
  id: string;
  name: string;
  price: number; // in cents
  image?: string;
  category?: string;
}

interface ProductGridProps {
  products: Product[];
  onProductClick: (product: Product) => void;
  className?: string;
}

export function ProductGrid({
  products,
  onProductClick,
  className,
}: ProductGridProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4",
        className
      )}
    >
      {products.map((product) => (
        <ProductCard
          key={product.id}
          id={product.id}
          name={product.name}
          price={product.price}
          image={product.image}
          onClick={() => onProductClick(product)}
        />
      ))}
    </div>
  );
}
