'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface FilterOption {
  label: string;
  value: string;
  count?: number;
}

interface FilterBarProps {
  options: FilterOption[];
  active: string | string[];
  onChange: (value: string) => void;
  multi?: boolean;
  className?: string;
  onClear?: () => void;
}

export default function FilterBar({
  options,
  active,
  onChange,
  multi = false,
  className,
  onClear,
}: FilterBarProps) {
  const activeValues = Array.isArray(active) ? active : active ? [active] : [];

  const isActive = (value: string) => activeValues.includes(value);

  const hasActive = activeValues.length > 0;

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      {options.map((opt) => {
        const active = isActive(opt.value);
        return (
          <motion.button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            whileTap={{ scale: 0.95 }}
            className={cn(
              'relative inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 select-none',
              active
                ? 'text-indigo-300'
                : 'text-slate-400 hover:text-slate-200'
            )}
            style={
              active
                ? {
                    background: 'rgba(99,102,241,0.2)',
                    border: '1px solid rgba(99,102,241,0.4)',
                    boxShadow: '0 0 10px rgba(99,102,241,0.15)',
                  }
                : {
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.08)',
                  }
            }
          >
            {opt.label}
            {opt.count !== undefined && (
              <span
                className={cn(
                  'px-1.5 py-0.5 rounded-full text-xs font-semibold',
                  active ? 'bg-indigo-500/30 text-indigo-300' : 'bg-white/10 text-slate-400'
                )}
              >
                {opt.count}
              </span>
            )}
          </motion.button>
        );
      })}

      {hasActive && onClear && (
        <motion.button
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.8 }}
          onClick={onClear}
          className="inline-flex items-center gap-1 px-2 py-1.5 rounded-full text-xs text-slate-400 hover:text-red-400 transition-colors"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)' }}
        >
          <X size={11} />
          Clear
        </motion.button>
      )}
    </div>
  );
}
