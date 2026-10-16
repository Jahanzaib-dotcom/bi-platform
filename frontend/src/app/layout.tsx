'use client';

import type { Metadata } from 'next';
import { Inter, Space_Grotesk } from 'next/font/google';
import { ThemeProvider } from 'next-themes';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { useState } from 'react';
import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-space-grotesk',
  display: 'swap',
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            retry: (failureCount, error: unknown) => {
              const axiosError = error as { response?: { status?: number } };
              if (axiosError?.response?.status === 401) return false;
              if (axiosError?.response?.status === 403) return false;
              return failureCount < 3;
            },
          },
        },
      })
  );

  return (
    <html
      lang="en"
      className={`${inter.variable} ${spaceGrotesk.variable}`}
      suppressHydrationWarning
    >
      <head>
        <link rel="icon" href="/favicon.ico" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#0A0A0F" />
      </head>
      <body className="bg-dark text-text-primary font-sans antialiased min-h-screen">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <QueryClientProvider client={queryClient}>
            {children}
            <Toaster
              position="top-right"
              gutter={12}
              containerClassName="z-[100]"
              toastOptions={{
                duration: 4000,
                style: {
                  background: '#12121A',
                  color: '#F8F8FF',
                  border: '1px solid #1E1E2E',
                  borderRadius: '12px',
                  fontSize: '14px',
                  fontFamily: 'var(--font-inter)',
                  boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
                  padding: '12px 16px',
                },
                success: {
                  iconTheme: {
                    primary: '#10B981',
                    secondary: '#0A0A0F',
                  },
                },
                error: {
                  iconTheme: {
                    primary: '#EF4444',
                    secondary: '#0A0A0F',
                  },
                },
                loading: {
                  iconTheme: {
                    primary: '#6366F1',
                    secondary: '#0A0A0F',
                  },
                },
              }}
            />
          </QueryClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
