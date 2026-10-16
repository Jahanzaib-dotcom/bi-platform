'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, Lock, Eye, EyeOff, User, AlertCircle, Loader2, CheckCircle2 } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import AuthLayout from '@/components/layouts/AuthLayout';
import { useAuth } from '@/hooks/useAuth';

const registerSchema = z
  .object({
    firstName: z
      .string()
      .min(1, 'First name is required')
      .max(50, 'First name is too long'),
    lastName: z
      .string()
      .min(1, 'Last name is required')
      .max(50, 'Last name is too long'),
    email: z.string().email('Please enter a valid email address'),
    password: z
      .string()
      .min(8, 'Password must be at least 8 characters')
      .regex(/[A-Z]/, 'Must contain at least one uppercase letter')
      .regex(/[0-9]/, 'Must contain at least one number'),
    confirmPassword: z.string().min(1, 'Please confirm your password'),
  })
  .refine((d) => d.password === d.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match',
  });

type RegisterForm = z.infer<typeof registerSchema>;

interface StrengthRule {
  label: string;
  test: (p: string) => boolean;
}

const strengthRules: StrengthRule[] = [
  { label: '8+ characters', test: (p) => p.length >= 8 },
  { label: 'Uppercase letter', test: (p) => /[A-Z]/.test(p) },
  { label: 'Number', test: (p) => /[0-9]/.test(p) },
  { label: 'Special character', test: (p) => /[^a-zA-Z0-9]/.test(p) },
];

function getStrengthLevel(password: string): { level: number; label: string; color: string } {
  const passed = strengthRules.filter((r) => r.test(password)).length;
  if (passed === 0) return { level: 0, label: '', color: '' };
  if (passed === 1) return { level: 1, label: 'Weak', color: '#ef4444' };
  if (passed === 2) return { level: 2, label: 'Fair', color: '#f59e0b' };
  if (passed === 3) return { level: 3, label: 'Good', color: '#6366f1' };
  return { level: 4, label: 'Strong', color: '#10b981' };
}

interface FormFieldProps {
  label: string;
  error?: string;
  children: React.ReactNode;
}

function FormField({ label, error, children }: FormFieldProps) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-400 mb-1.5">{label}</label>
      {children}
      <AnimatePresence>
        {error && (
          <motion.p
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-1 text-xs text-red-400 flex items-center gap-1"
          >
            <AlertCircle size={11} />
            {error}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

const inputBase =
  'w-full py-2.5 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 transition-all';

export default function RegisterPage() {
  const { register: registerUser, isLoading } = useAuth();

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [passwordValue, setPasswordValue] = useState('');

  const strength = getStrengthLevel(passwordValue);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  });

  const watchedPassword = watch('password', '');
  useEffect(() => {
    setPasswordValue(watchedPassword || '');
  }, [watchedPassword]);

  const onSubmit = async (data: RegisterForm) => {
    setServerError(null);
    try {
      await registerUser({
        firstName: data.firstName,
        lastName: data.lastName,
        email: data.email,
        password: data.password,
      });
    } catch (err: unknown) {
      const e = err as { message?: string };
      setServerError(e?.message || 'Registration failed. Please try again.');
    }
  };

  const busy = isSubmitting || isLoading;

  const inputStyle = (hasError: boolean) => ({
    background: 'rgba(255,255,255,0.05)',
    border: `1px solid ${hasError ? 'rgba(239,68,68,0.5)' : 'rgba(255,255,255,0.1)'}`,
  });

  return (
    <AuthLayout>
      <div className="px-8 py-7">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="text-center mb-7"
        >
          <h1 className="text-2xl font-bold text-white mb-1.5">Create account</h1>
          <p className="text-sm text-slate-400">Join BI Platform — it&apos;s free to get started</p>
        </motion.div>

        <motion.form
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          onSubmit={handleSubmit(onSubmit)}
          className="space-y-4"
        >
          {/* Server Error */}
          <AnimatePresence>
            {serverError && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="flex items-start gap-2.5 p-3 rounded-lg text-sm text-red-300"
                style={{
                  background: 'rgba(239,68,68,0.1)',
                  border: '1px solid rgba(239,68,68,0.25)',
                }}
              >
                <AlertCircle size={15} className="flex-shrink-0 mt-0.5 text-red-400" />
                <span>{serverError}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Name row */}
          <div className="grid grid-cols-2 gap-3">
            <FormField label="First name" error={errors.firstName?.message}>
              <div className="relative">
                <User size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                <input
                  {...register('firstName')}
                  type="text"
                  placeholder="Jane"
                  autoComplete="given-name"
                  className={`${inputBase} pl-9 pr-3`}
                  style={inputStyle(!!errors.firstName)}
                />
              </div>
            </FormField>

            <FormField label="Last name" error={errors.lastName?.message}>
              <input
                {...register('lastName')}
                type="text"
                placeholder="Smith"
                autoComplete="family-name"
                className={`${inputBase} px-3`}
                style={inputStyle(!!errors.lastName)}
              />
            </FormField>
          </div>

          {/* Email */}
          <FormField label="Email address" error={errors.email?.message}>
            <div className="relative">
              <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                {...register('email')}
                type="email"
                placeholder="you@company.com"
                autoComplete="email"
                className={`${inputBase} pl-9 pr-4`}
                style={inputStyle(!!errors.email)}
              />
            </div>
          </FormField>

          {/* Password */}
          <FormField label="Password" error={errors.password?.message}>
            <div className="relative">
              <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                {...register('password')}
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••"
                autoComplete="new-password"
                className={`${inputBase} pl-9 pr-10`}
                style={inputStyle(!!errors.password)}
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>

            {/* Password Strength Indicator */}
            {passwordValue.length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="mt-2 space-y-2"
              >
                <div className="flex items-center gap-2">
                  <div className="flex gap-1 flex-1">
                    {[1, 2, 3, 4].map((lvl) => (
                      <div
                        key={lvl}
                        className="flex-1 h-1 rounded-full transition-all duration-300"
                        style={{
                          background:
                            strength.level >= lvl
                              ? strength.color
                              : 'rgba(255,255,255,0.08)',
                        }}
                      />
                    ))}
                  </div>
                  {strength.label && (
                    <span className="text-xs font-medium" style={{ color: strength.color }}>
                      {strength.label}
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-1">
                  {strengthRules.map((rule) => {
                    const passed = rule.test(passwordValue);
                    return (
                      <div key={rule.label} className="flex items-center gap-1.5">
                        <CheckCircle2
                          size={11}
                          className={passed ? 'text-emerald-400' : 'text-slate-600'}
                        />
                        <span className={`text-xs ${passed ? 'text-slate-300' : 'text-slate-500'}`}>
                          {rule.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </FormField>

          {/* Confirm Password */}
          <FormField label="Confirm password" error={errors.confirmPassword?.message}>
            <div className="relative">
              <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                {...register('confirmPassword')}
                type={showConfirm ? 'text' : 'password'}
                placeholder="••••••••"
                autoComplete="new-password"
                className={`${inputBase} pl-9 pr-10`}
                style={inputStyle(!!errors.confirmPassword)}
              />
              <button
                type="button"
                onClick={() => setShowConfirm((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
              >
                {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </FormField>

          {/* Submit */}
          <motion.button
            type="submit"
            disabled={busy}
            whileTap={{ scale: 0.98 }}
            className="w-full py-2.5 px-4 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-60 disabled:cursor-not-allowed mt-2"
            style={{
              background: busy
                ? 'rgba(99,102,241,0.5)'
                : 'linear-gradient(135deg, #6366f1, #7c3aed)',
              boxShadow: busy ? 'none' : '0 4px 16px rgba(99,102,241,0.35)',
            }}
          >
            {busy ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2 size={15} className="animate-spin" />
                Creating account...
              </span>
            ) : (
              'Create account'
            )}
          </motion.button>
        </motion.form>

        {/* Login link */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="mt-5 text-center text-sm text-slate-400"
        >
          Already have an account?{' '}
          <Link
            href="/auth/login"
            className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
          >
            Sign in
          </Link>
        </motion.p>
      </div>
    </AuthLayout>
  );
}
