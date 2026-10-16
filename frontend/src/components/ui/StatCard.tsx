'use client';

import React from 'react';
import CountUp from 'react-countup';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface StatCardProps {
  label: string;
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  change?: number;
  icon?: React.ReactNode;
  iconColor?: string;
  className?: string;
}

export default function StatCard({
  label,
  value,
  prefix = '',
  suffix = '',
  decimals = 0,
  change,
  icon,
  iconColor = 'text-indigo-400',
  className,
}: StatCardProps) {
  const isPositive = change !== undefined && change > 0;
  const isNegative = change !== undefined && change < 0;
  const isNeutral = change === 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.2 }}
      className={cn('relative rounded-xl overflow-hidden', className)}
      style={{
        background: 'rgba(14,14,32,0.6)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(255,255,255,0.07)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      }}
    >
      <div className="p-5">
        <div className="flex items-start justify-between mb-4">
          <p className="text-sm text-slate-400 font-medium">{label}</p>
          {icon && (
            <div
              className={cn(
                'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0',
                iconColor
              )}
              style={{ background: 'rgba(99,102,241,0.1)' }}
            >
              {icon}
            </div>
          )}
        </div>

        <div className="flex items-end justify-between">
          <div>
            <span className="text-2xl font-bold text-white">
              {prefix}
              <CountUp
                end={value}
                duration={1.5}
                decimals={decimals}
                separator=","
                useEasing
              />
              {suffix}
            </span>
          </div>

          {change !== undefined && (
            <div
              className={cn(
                'flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-full',
                isPositive && 'bg-emerald-500/15 text-emerald-400',
                isNegative && 'bg-red-500/15 text-red-400',
                isNeutral && 'bg-slate-500/15 text-slate-400'
              )}
            >
              {isPositive && <TrendingUp size={12} />}
              {isNegative && <TrendingDown size={12} />}
              {isNeutral && <Minus size={12} />}
              <span>
                {isPositive ? '+' : ''}{change}%
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Bottom accent line */}
      <div
        className="absolute bottom-0 left-0 right-0 h-0.5"
        style={{
          background: isPositive
            ? 'linear-gradient(90deg, transparent, rgba(16,185,129,0.5), transparent)'
            : isNegative
            ? 'linear-gradient(90deg, transparent, rgba(239,68,68,0.5), transparent)'
            : 'linear-gradient(90deg, transparent, rgba(99,102,241,0.4), transparent)',
        }}
      />
    </motion.div>
  );
}
