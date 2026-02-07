"use client";

import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface Column<T> {
  id: string;
  header: string;
  accessorFn: (row: T) => React.ReactNode;
  className?: string;
  headerClassName?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (row: T) => void;
  className?: string;
  emptyMessage?: string;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function DataTable<T>({
  columns,
  data,
  onRowClick,
  className,
  emptyMessage = "No data found.",
}: DataTableProps<T>) {
  return (
    <div
      className={cn(
        "w-full rounded-[var(--radius-m)] border border-[var(--border)]",
        "bg-[var(--card)] overflow-hidden",
        className
      )}
    >
      <table className="w-full border-collapse">
        {/* Header */}
        <thead>
          <tr className="border-b border-[var(--border)]">
            {columns.map((col) => (
              <th
                key={col.id}
                className={cn(
                  "px-4 py-3 text-start text-xs font-medium font-body",
                  "text-[var(--muted-foreground)] uppercase tracking-wider",
                  col.headerClassName
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>

        {/* Body */}
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-12 text-center text-sm text-[var(--muted-foreground)]"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, i) => (
              <tr
                key={i}
                onClick={() => onRowClick?.(row)}
                className={cn(
                  "border-b border-[var(--border)] last:border-b-0",
                  "transition-colors",
                  onRowClick && "cursor-pointer hover:bg-[var(--accent)]"
                )}
              >
                {columns.map((col) => (
                  <td
                    key={col.id}
                    className={cn(
                      "px-4 py-3 text-sm font-body text-[var(--foreground)]",
                      col.className
                    )}
                  >
                    {col.accessorFn(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
