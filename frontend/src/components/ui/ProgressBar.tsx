'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface ProgressBarProps {
  value: number; // 0-100
  max?: number;
  label?: string;
  showValue?: boolean;
  size?: 'sm' | 'md' | 'lg';
  color?: 'indigo' | 'emerald' | 'amber' | 'red' | 'purple' | 'auto';
  className?: string;
  animate?: boolean;
}

const colorMap: Record<string, string> = {
  indigo: 'linear-gradient(90deg, #6366f1, #818cf8)',
  emerald: 'linear-gradient(90deg, #10b981, #34d399)',
  amber: 'linear-gradient(90deg, #f59e0b, #fbbf24)',
  red: 'linear-gradient(90deg, #ef4444, #f87171)',
  purple: 'linear-gradient(90deg, #a855f7, #c084fc)',
};

const heightMap = {
  sm: 'h-1.5',
  md: 'h-2.5',
  lg: 'h-3.5',
};

function autoColor(value: number): string {
  if (value >= 70) return colorMap.emerald;
  if (value >= 40) return colorMap.amber;
  return colorMap.red;
}

export default function ProgressBar({
  value,
  max = 100,
  label,
  showValue = false,
  size = 'md',
  color = 'indigo',
  className,
  animate = true,
}: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const [displayPct, setDisplayPct] = useState(animate ? 0 : pct);

  useEffect(() => {
    if (animate) {
      const t = setTimeout(() => setDisplayPct(pct), 80);
      return () => clearTimeout(t);
    }
    setDisplayPct(pct);
  }, [pct, animate]);

  const gradient = color === 'auto' ? autoColor(pct) : colorMap[color] || colorMap.indigo;

  return (
    <div className={cn('w-full', className)}>
      {(label || showValue) && (
        <div className="flex items-center justify-between mb-1.5">
          {label && <span className="text-xs text-slate-400">{label}</span>}
          {showValue && (
            <span className="text-xs font-medium text-slate-300">{Math.round(pct)}%</span>
          )}
        </div>
      )}
      <div
        className={cn('w-full rounded-full overflow-hidden', heightMap[size])}
        style={{ background: 'rgba(255,255,255,0.06)' }}
      >
        <motion.div
          className="h-full rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${displayPct}%` }}
          transition={{ duration: animate ? 0.8 : 0, ease: 'easeOut' }}
          style={{
            background: gradient,
            boxShadow: `0 0 8px ${color === 'auto' ? 'rgba(99,102,241,0.4)' : 'rgba(99,102,241,0.4)'}`,
          }}
        />
      </div>
    </div>
  );
}
