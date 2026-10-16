'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn('flex flex-col items-center justify-center py-16 px-6 text-center', className)}
    >
      {icon && (
        <motion.div
          initial={{ scale: 0.8 }}
          animate={{ scale: 1 }}
          transition={{ duration: 0.3, delay: 0.1 }}
          className="mb-5 relative"
        >
          {/* Glow circle behind icon */}
          <div className="absolute inset-0 bg-indigo-500/10 rounded-full blur-xl scale-150" />
          <div
            className="relative w-16 h-16 rounded-2xl flex items-center justify-center text-slate-400"
            style={{
              background: 'rgba(99,102,241,0.08)',
              border: '1px solid rgba(99,102,241,0.15)',
            }}
          >
            {icon}
          </div>
        </motion.div>
      )}

      <motion.h3
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.15 }}
        className="text-base font-semibold text-white mb-2"
      >
        {title}
      </motion.h3>

      {description && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="text-sm text-slate-400 max-w-xs"
        >
          {description}
        </motion.p>
      )}

      {action && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="mt-5"
        >
          {action}
        </motion.div>
      )}
    </motion.div>
  );
}

