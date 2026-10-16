'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store';
import LoadingSpinner from '@/components/ui/LoadingSpinner';

export default function RootPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    const token = localStorage.getItem('bi_access_token');
    if (isAuthenticated && token) {
      router.replace('/dashboard');
    } else {
      router.replace('/auth/login');
    }
  }, [isAuthenticated, router]);

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <LoadingSpinner size="lg" label="Loading..." />
    </div>
  );
}
