'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  glow?: boolean;
  glowColor?: string;
  hover?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  onClick?: () => void;
}

const paddingMap = {
  none: 'p-0',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-6',
};

export default function GlassCard({
  children,
  className,
  glow = false,
  glowColor = 'rgba(99,102,241,0.15)',
  hover = false,
  padding = 'md',
  onClick,
}: GlassCardProps) {
  const Comp = hover || onClick ? motion.div : 'div';
  const motionProps =
    hover || onClick
      ? {
          whileHover: { y: -3, boxShadow: `0 20px 40px rgba(0,0,0,0.4), 0 0 0 1px rgba(99,102,241,0.15)` },
          transition: { duration: 0.2 },
        }
      : {};

  return (
    <Comp
      {...(motionProps as any)}
      onClick={onClick}
      className={cn(
        'relative rounded-xl overflow-hidden',
        paddingMap[padding],
        onClick && 'cursor-pointer',
        className
      )}
      style={{
        background: 'rgba(14,14,32,0.6)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(255,255,255,0.07)',
        boxShadow: glow
          ? `0 8px 32px rgba(0,0,0,0.3), 0 0 20px ${glowColor}`
          : '0 8px 32px rgba(0,0,0,0.3)',
      }}
    >
      {children}
    </Comp>
  );
}
