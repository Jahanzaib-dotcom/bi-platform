'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface ScoreRingProps {
  score: number; // 0-100
  size?: number;
  strokeWidth?: number;
  label?: string;
  showValue?: boolean;
  className?: string;
  animate?: boolean;
}

function getColor(score: number): { stroke: string; glow: string; text: string } {
  if (score >= 70) {
    return {
      stroke: 'url(#scoreGradientGreen)',
      glow: 'rgba(16,185,129,0.4)',
      text: 'text-emerald-400',
    };
  }
  if (score >= 40) {
    return {
      stroke: 'url(#scoreGradientYellow)',
      glow: 'rgba(245,158,11,0.4)',
      text: 'text-amber-400',
    };
  }
  return {
    stroke: 'url(#scoreGradientRed)',
    glow: 'rgba(239,68,68,0.4)',
    text: 'text-red-400',
  };
}

export default function ScoreRing({
  score,
  size = 80,
  strokeWidth = 6,
  label,
  showValue = true,
  className,
  animate = true,
}: ScoreRingProps) {
  const clampedScore = Math.min(100, Math.max(0, score));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clampedScore / 100) * circumference;
  const color = getColor(clampedScore);

  const [displayOffset, setDisplayOffset] = useState(circumference);

  useEffect(() => {
    if (animate) {
      const timer = setTimeout(() => setDisplayOffset(offset), 100);
      return () => clearTimeout(timer);
    } else {
      setDisplayOffset(offset);
    }
  }, [offset, animate]);

  const cx = size / 2;
  const cy = size / 2;
  const uniqueId = `ring-${score}`;

  return (
    <div className={cn('relative inline-flex flex-col items-center gap-1', className)}>
      <svg width={size} height={size} style={{ filter: `drop-shadow(0 0 8px ${color.glow})` }}>
        <defs>
          <linearGradient id="scoreGradientGreen" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#34d399" />
            <stop offset="100%" stopColor="#10b981" />
          </linearGradient>
          <linearGradient id="scoreGradientYellow" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#fbbf24" />
            <stop offset="100%" stopColor="#f59e0b" />
          </linearGradient>
          <linearGradient id="scoreGradientRed" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#f87171" />
            <stop offset="100%" stopColor="#ef4444" />
          </linearGradient>
        </defs>

        {/* Background track */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={strokeWidth}
        />

        {/* Progress arc */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={color.stroke}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={displayOffset}
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{
            transition: animate ? 'stroke-dashoffset 1s cubic-bezier(0.4, 0, 0.2, 1)' : 'none',
          }}
        />

        {/* Center value */}
        {showValue && (
          <text
            x={cx}
            y={cy + 1}
            textAnchor="middle"
            dominantBaseline="middle"
            className="font-bold"
            fontSize={size / 4}
            fill="white"
          >
            {clampedScore}
          </text>
        )}
      </svg>

      {label && (
        <span className="text-xs text-slate-400 text-center">{label}</span>
      )}
    </div>
  );
}
