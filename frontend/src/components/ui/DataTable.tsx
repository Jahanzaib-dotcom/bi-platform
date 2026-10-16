'use client';

import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface Column<T> {
  key: keyof T | string;
  header: string;
  accessor?: (row: T) => React.ReactNode;
  sortable?: boolean;
  width?: string;
  align?: 'left' | 'center' | 'right';
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  pageSize?: number;
  keyField?: keyof T;
  className?: string;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
}

type SortDir = 'asc' | 'desc' | null;

function SkeletonRow({ cols }: { cols: number }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div
            className="h-4 rounded"
            style={{
              background: 'rgba(255,255,255,0.05)',
              width: `${60 + Math.random() * 30}%`,
              animation: 'pulse 1.5s ease-in-out infinite',
            }}
          />
        </td>
      ))}
    </tr>
  );
}

export default function DataTable<T extends Record<string, any>>({
  columns,
  data,
  loading = false,
  pageSize = 10,
  keyField,
  className,
  emptyMessage = 'No data available',
  onRowClick,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);
  const [page, setPage] = useState(1);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : d === 'desc' ? null : 'asc'));
      if (sortDir === 'desc') setSortKey(null);
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sorted = useMemo(() => {
    if (!sortKey || !sortDir) return data;
    return [...data].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  const totalPages = Math.ceil(sorted.length / pageSize);
  const paged = sorted.slice((page - 1) * pageSize, page * pageSize);

  const getCellValue = (row: T, col: Column<T>): React.ReactNode => {
    if (col.accessor) return col.accessor(row);
    const key = col.key as string;
    return row[key] ?? '—';
  };

  return (
    <div className={cn('rounded-xl overflow-hidden', className)} style={{
      background: 'rgba(14,14,32,0.6)',
      backdropFilter: 'blur(16px)',
      border: '1px solid rgba(255,255,255,0.07)',
    }}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              {columns.map((col) => (
                <th
                  key={col.key as string}
                  className={cn(
                    'px-4 py-3 font-medium text-slate-400 whitespace-nowrap',
                    col.align === 'center' && 'text-center',
                    col.align === 'right' && 'text-right',
                    !col.align && 'text-left',
                    col.sortable && 'cursor-pointer select-none hover:text-white transition-colors'
                  )}
                  style={{ width: col.width }}
                  onClick={() => col.sortable && handleSort(col.key as string)}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.header}
                    {col.sortable && (
                      <span className="text-slate-600">
                        {sortKey === col.key ? (
                          sortDir === 'asc' ? <ChevronUp size={13} className="text-indigo-400" /> : <ChevronDown size={13} className="text-indigo-400" />
                        ) : (
                          <ChevronsUpDown size={13} />
                        )}
                      </span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <SkeletonRow key={i} cols={columns.length} />
              ))
            ) : paged.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12 text-center text-slate-400 text-sm">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              <AnimatePresence mode="sync">
                {paged.map((row, idx) => (
                  <motion.tr
                    key={keyField ? String(row[keyField as string]) : idx}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.15, delay: idx * 0.03 }}
                    onClick={() => onRowClick?.(row)}
                    className={cn(
                      'transition-colors',
                      onRowClick && 'cursor-pointer',
                    )}
                    style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
                    whileHover={onRowClick ? { backgroundColor: 'rgba(99,102,241,0.05)' } : undefined}
                  >
                    {columns.map((col) => (
                      <td
                        key={col.key as string}
                        className={cn(
                          'px-4 py-3 text-slate-300',
                          col.align === 'center' && 'text-center',
                          col.align === 'right' && 'text-right'
                        )}
                      >
                        {getCellValue(row, col)}
                      </td>
                    ))}
                  </motion.tr>
                ))}
              </AnimatePresence>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!loading && totalPages > 1 && (
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}
        >
          <span className="text-xs text-slate-400">
            Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, sorted.length)} of {sorted.length}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            {Array.from({ length: Math.min(5, totalPages) }).map((_, i) => {
              const pg = i + 1;
              return (
                <button
                  key={pg}
                  onClick={() => setPage(pg)}
                  className={cn(
                    'w-7 h-7 rounded text-xs font-medium transition-colors',
                    page === pg
                      ? 'bg-indigo-500/30 text-indigo-300 border border-indigo-500/40'
                      : 'text-slate-400 hover:text-white hover:bg-white/5'
                  )}
                >
                  {pg}
                </button>
              );
            })}
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
