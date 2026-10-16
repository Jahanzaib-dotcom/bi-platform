'use client';

import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { authApi, setTokens, clearTokens } from '@/lib/api';
import { useAuthStore } from '@/store';
import type { LoginCredentials, RegisterPayload, User } from '@/types';

export const authQueryKeys = {
  me: ['auth', 'me'] as const,
};

interface UseAuthReturn {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isFetchingUser: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  updateProfile: (payload: Partial<User>) => Promise<void>;
}

export function useAuth(): UseAuthReturn {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user, isAuthenticated, setAuth, logout: storeLogout, setUser, setLoading } = useAuthStore();

  const isFetchingUser = false;

  const loginMutation = useMutation({
    mutationFn: authApi.login,
    onSuccess: async ({ access_token, refresh_token }) => {
      setTokens(access_token, refresh_token);
      let me: User;
      try {
        me = await authApi.me();
      } catch {
        me = { email: '' } as User;
      }
      setAuth(me, access_token, refresh_token);
      toast.success('Welcome back!');
      setTimeout(() => { window.location.href = '/dashboard'; }, 200);
    },
    onError: (error: { message?: string }) => {
      toast.error(error.message ?? 'Login failed. Please check your credentials.');
    },
  });

  const registerMutation = useMutation({
    mutationFn: authApi.register,
    onSuccess: async ({ access_token, refresh_token }) => {
      setTokens(access_token, refresh_token);
      let me: User;
      try {
        me = await authApi.me();
      } catch {
        me = { email: '' } as User;
      }
      setAuth(me, access_token, refresh_token);
      toast.success('Welcome to BI Platform!');
      router.push('/dashboard');
    },
    onError: (error: { message?: string }) => {
      toast.error(error.message ?? 'Registration failed. Please try again.');
    },
  });

  const logoutMutation = useMutation({
    mutationFn: authApi.logout,
    onSettled: () => {
      clearTokens();
      storeLogout();
      queryClient.clear();
      router.push('/auth/login');
      toast.success('Signed out successfully.');
    },
  });

  const updateProfileMutation = useMutation({
    mutationFn: authApi.updateProfile,
    onSuccess: (updatedUser) => {
      setUser(updatedUser);
      queryClient.setQueryData(authQueryKeys.me, updatedUser);
      toast.success('Profile updated successfully.');
    },
    onError: (error: { message?: string }) => {
      toast.error(error.message ?? 'Failed to update profile.');
    },
  });

  const login = useCallback(
    async (credentials: LoginCredentials) => {
      await loginMutation.mutateAsync(credentials);
    },
    [loginMutation]
  );

  const logout = useCallback(async () => {
    await logoutMutation.mutateAsync();
  }, [logoutMutation]);

  const register = useCallback(
    async (payload: RegisterPayload) => {
      await registerMutation.mutateAsync(payload);
    },
    [registerMutation]
  );

  const updateProfile = useCallback(
    async (payload: Partial<User>) => {
      await updateProfileMutation.mutateAsync(payload);
    },
    [updateProfileMutation]
  );

  const isLoading =
    loginMutation.isPending ||
    registerMutation.isPending ||
    logoutMutation.isPending ||
    updateProfileMutation.isPending;

  return {
    user,
    isAuthenticated,
    isLoading,
    isFetchingUser,
    login,
    logout,
    register,
    updateProfile,
  };
}

export default useAuth;
