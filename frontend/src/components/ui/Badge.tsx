'use client';

import React from 'react';
import { cn } from '@/lib/utils';

type BadgeVariant =
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'purple'
  | 'slate';

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  dot?: boolean;
  size?: 'sm' | 'md';
  className?: string;
}

const variantStyles: Record<BadgeVariant, { bg: string; text: string; dot: string }> = {
  default: {
    bg: 'bg-indigo-500/15 border border-indigo-500/20',
    text: 'text-indigo-400',
    dot: 'bg-indigo-400',
  },
  success: {
    bg: 'bg-emerald-500/15 border border-emerald-500/20',
    text: 'text-emerald-400',
    dot: 'bg-emerald-400',
  },
  warning: {
    bg: 'bg-amber-500/15 border border-amber-500/20',
    text: 'text-amber-400',
    dot: 'bg-amber-400',
  },
  danger: {
    bg: 'bg-red-500/15 border border-red-500/20',
    text: 'text-red-400',
    dot: 'bg-red-400',
  },
  info: {
    bg: 'bg-sky-500/15 border border-sky-500/20',
    text: 'text-sky-400',
    dot: 'bg-sky-400',
  },
  purple: {
    bg: 'bg-purple-500/15 border border-purple-500/20',
    text: 'text-purple-400',
    dot: 'bg-purple-400',
  },
  slate: {
    bg: 'bg-slate-500/15 border border-slate-500/20',
    text: 'text-slate-400',
    dot: 'bg-slate-400',
  },
};

const sizeStyles = {
  sm: 'px-1.5 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-xs',
};

export default function Badge({
  children,
  variant = 'default',
  dot = false,
  size = 'md',
  className,
}: BadgeProps) {
  const styles = variantStyles[variant];

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        styles.bg,
        styles.text,
        sizeStyles[size],
        className
      )}
    >
      {dot && (
        <span
          className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', styles.dot)}
        />
      )}
      {children}
    </span>
  );
}
