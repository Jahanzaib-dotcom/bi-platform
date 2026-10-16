'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, Lock, Eye, EyeOff, BarChart3, AlertCircle, Loader2 } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import AuthLayout from '@/components/layouts/AuthLayout';
import { useAuth } from '@/hooks/useAuth';

const loginSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
  rememberMe: z.boolean().optional(),
});

type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const { login } = useAuth();


  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { rememberMe: false },
  });

  const onSubmit = async (data: LoginForm) => {
    setServerError(null);
    try {
      await login({ email: data.email, password: data.password });
    } catch (err: unknown) {
      const e = err as { message?: string };
      setServerError(e?.message || 'Invalid email or password');
    }
  };

  const busy = isSubmitting;

  return (
    <AuthLayout>
      <div className="px-8 py-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="text-center mb-8"
        >
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <BarChart3 size={18} className="text-white" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-white mb-1.5">Welcome back</h1>
          <p className="text-sm text-slate-400">Sign in to your BI Platform account</p>
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
                initial={{ opacity: 0, height: 0, y: -4 }}
                animate={{ opacity: 1, height: 'auto', y: 0 }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
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

          {/* Email */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Email address
            </label>
            <div className="relative">
              <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                {...register('email')}
                type="email"
                placeholder="you@company.com"
                autoComplete="email"
                className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 transition-all"
                style={{
                  background: 'rgba(255,255,255,0.05)',
                  border: `1px solid ${errors.email ? 'rgba(239,68,68,0.5)' : 'rgba(255,255,255,0.1)'}`,
                }}
              />
            </div>
            <AnimatePresence>
              {errors.email && (
                <motion.p
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-1 text-xs text-red-400 flex items-center gap-1"
                >
                  <AlertCircle size={11} />
                  {errors.email.message}
                </motion.p>
              )}
            </AnimatePresence>
          </div>

          {/* Password */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Password
            </label>
            <div className="relative">
              <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                {...register('password')}
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••"
                autoComplete="current-password"
                className="w-full pl-9 pr-10 py-2.5 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 transition-all"
                style={{
                  background: 'rgba(255,255,255,0.05)',
                  border: `1px solid ${errors.password ? 'rgba(239,68,68,0.5)' : 'rgba(255,255,255,0.1)'}`,
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
            <AnimatePresence>
              {errors.password && (
                <motion.p
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-1 text-xs text-red-400 flex items-center gap-1"
                >
                  <AlertCircle size={11} />
                  {errors.password.message}
                </motion.p>
              )}
            </AnimatePresence>
          </div>

          {/* Remember me + Forgot password */}
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer group">
              <div className="relative">
                <input
                  {...register('rememberMe')}
                  type="checkbox"
                  className="sr-only peer"
                />
                <div
                  className="w-4 h-4 rounded border transition-all peer-checked:bg-indigo-500 peer-checked:border-indigo-500 group-hover:border-indigo-400"
                  style={{ border: '1px solid rgba(255,255,255,0.2)' }}
                />
                <svg
                  className="absolute top-0.5 left-0.5 w-3 h-3 text-white pointer-events-none opacity-0 peer-checked:opacity-100 transition-opacity"
                  viewBox="0 0 12 12"
                  fill="none"
                >
                  <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <span className="text-xs text-slate-400 group-hover:text-slate-300 transition-colors select-none">
                Remember me
              </span>
            </label>
            <Link
              href="/auth/forgot-password"
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              Forgot password?
            </Link>
          </div>

          {/* Submit */}
          <motion.button
            type="submit"
            disabled={busy}
            whileTap={{ scale: 0.98 }}
            className="w-full py-2.5 px-4 rounded-lg text-sm font-semibold text-white transition-all relative overflow-hidden disabled:opacity-60 disabled:cursor-not-allowed"
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
                Signing in...
              </span>
            ) : (
              'Sign in'
            )}
          </motion.button>
        </motion.form>

        {/* Register link */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="mt-6 text-center text-sm text-slate-400"
        >
          Don&apos;t have an account?{' '}
          <Link
            href="/auth/register"
            className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
          >
            Create account
          </Link>
        </motion.p>
      </div>
    </AuthLayout>
  );
}
