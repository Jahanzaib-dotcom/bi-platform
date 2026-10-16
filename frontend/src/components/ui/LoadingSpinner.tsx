'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  label?: string;
  fullScreen?: boolean;
}

const sizeMap = {
  sm: 20,
  md: 32,
  lg: 48,
  xl: 64,
};

export default function LoadingSpinner({
  size = 'md',
  className,
  label,
  fullScreen = false,
}: LoadingSpinnerProps) {
  const dim = sizeMap[size];
  const strokeWidth = dim / 10;
  const radius = (dim - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const cx = dim / 2;
  const cy = dim / 2;

  const spinner = (
    <div className={cn('flex flex-col items-center gap-3', className)}>
      <div className="relative" style={{ width: dim, height: dim }}>
        <svg width={dim} height={dim}>
          {/* Track */}
          <circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke="rgba(99,102,241,0.15)"
            strokeWidth={strokeWidth}
          />
          {/* Animated arc */}
          <motion.circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke="url(#spinnerGradient)"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * 0.75}
            animate={{ rotate: 360 }}
            transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
            style={{ transformOrigin: `${cx}px ${cy}px` }}
          />
          <defs>
            <linearGradient id="spinnerGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#a855f7" />
            </linearGradient>
          </defs>
        </svg>

        {/* Center glow dot */}
        <motion.div
          className="absolute inset-0 flex items-center justify-center"
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.6, repeat: Infinity }}
        >
          <div
            className="rounded-full bg-indigo-500"
            style={{ width: dim * 0.15, height: dim * 0.15, boxShadow: `0 0 ${dim * 0.2}px rgba(99,102,241,0.8)` }}
          />
        </motion.div>
      </div>
      {label && (
        <motion.p
          className="text-sm text-slate-400"
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 1.6, repeat: Infinity }}
        >
          {label}
        </motion.p>
      )}
    </div>
  );

  if (fullScreen) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm z-50">
        {spinner}
      </div>
    );
  }

  return spinner;
}
