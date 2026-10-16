'use client';

import React, { useRef } from 'react';
import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  inputClassName?: string;
  onClear?: () => void;
  autoFocus?: boolean;
  disabled?: boolean;
}

export default function SearchInput({
  value,
  onChange,
  placeholder = 'Search...',
  className,
  inputClassName,
  onClear,
  autoFocus,
  disabled,
}: SearchInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleClear = () => {
    onChange('');
    onClear?.();
    inputRef.current?.focus();
  };

  return (
    <div className={cn('relative flex items-center', className)}>
      <Search
        size={15}
        className="absolute left-3 text-slate-400 pointer-events-none flex-shrink-0"
      />
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        disabled={disabled}
        className={cn(
          'w-full pl-9 pr-9 py-2 rounded-lg text-sm text-slate-200 placeholder-slate-500 transition-all',
          'focus:outline-none focus:ring-2 focus:ring-indigo-500/40',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          inputClassName
        )}
        style={{
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.1)',
        }}
        onFocus={(e) => {
          e.currentTarget.style.background = 'rgba(255,255,255,0.07)';
          e.currentTarget.style.borderColor = 'rgba(99,102,241,0.4)';
        }}
        onBlur={(e) => {
          e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
          e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)';
        }}
      />
      {value && (
        <button
          onClick={handleClear}
          className="absolute right-3 text-slate-400 hover:text-white transition-colors"
          type="button"
          aria-label="Clear search"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
