'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  Terminal,
  Search,
  ScanSearch,
  Target,
  BarChart3,
  Settings,
  ChevronLeft,
  ChevronRight,
  Bell,
  LogOut,
  User,
  Menu,
  X,
  ChevronDown,
  Users,
  Briefcase,
  Mail,
  FileText,
} from 'lucide-react';
import { useAuthStore } from '@/store';

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', icon: <LayoutDashboard size={20} /> },
  { label: 'Command Center', href: '/dashboard/command-center', icon: <Terminal size={20} /> },
  { label: 'Discovery', href: '/dashboard/discovery', icon: <Search size={20} /> },
  { label: 'Freelance Hub', href: '/dashboard/freelance', icon: <Briefcase size={20} /> },
  { label: 'Audit Center', href: '/dashboard/audit', icon: <ScanSearch size={20} /> },
  { label: 'Lead Intelligence', href: '/dashboard/leads', icon: <Target size={20} /> },
  { label: 'Contacts', href: '/dashboard/contacts', icon: <Users size={20} /> },
  { label: 'CRM', href: '/dashboard/crm', icon: <Briefcase size={20} /> },
  { label: 'Outreach', href: '/dashboard/outreach', icon: <Mail size={20} /> },
  { label: 'Proposals', href: '/dashboard/proposals', icon: <FileText size={20} /> },
  { label: 'Analytics', href: '/dashboard/analytics', icon: <BarChart3 size={20} /> },
  { label: 'Settings', href: '/dashboard/settings', icon: <Settings size={20} /> },
];

function getPageTitle(pathname: string): string {
  const item = navItems.find((n) => n.href === pathname);
  if (item) return item.label;
  if (pathname.startsWith('/dashboard/command-center')) return 'Command Center';
  if (pathname.startsWith('/dashboard/discovery')) return 'Discovery';
  if (pathname.startsWith('/dashboard/freelance')) return 'Freelance Hub';
  if (pathname.startsWith('/dashboard/audit')) return 'Audit Center';
  if (pathname.startsWith('/dashboard/leads')) return 'Lead Intelligence';
  if (pathname.startsWith('/dashboard/contacts')) return 'Contacts';
  if (pathname.startsWith('/dashboard/crm')) return 'CRM';
  if (pathname.startsWith('/dashboard/outreach')) return 'Outreach';
  if (pathname.startsWith('/dashboard/proposals')) return 'Proposals';
  if (pathname.startsWith('/dashboard/analytics')) return 'Analytics';
  if (pathname.startsWith('/dashboard/settings')) return 'Settings';
  return 'Dashboard';
}

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();

  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClick = () => {
      setUserMenuOpen(false);
      setNotifOpen(false);
    };
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, []);

  const handleLogout = () => {
    logout();
    router.push('/auth/login');
  };

  const sidebarW = collapsed ? 64 : 256;

  const SidebarContent = ({ isMobile = false }: { isMobile?: boolean }) => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-white/10 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 shadow-lg shadow-indigo-500/30">
            <BarChart3 size={16} className="text-white" />
          </div>
          {(!collapsed || isMobile) && (
            <motion.span
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              className="font-bold text-lg bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent whitespace-nowrap overflow-hidden"
            >
              BI Platform
            </motion.span>
          )}
        </div>
        {!isMobile && (
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="ml-auto text-slate-400 hover:text-white transition-colors flex-shrink-0"
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        )}
      </div>

      {/* Nav Items */}
      <nav className="flex-1 overflow-y-auto py-4 space-y-1 px-2">
        {navItems.map((item) => {
          const isActive =
            item.href === '/dashboard'
              ? pathname === '/dashboard'
              : pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href}>
              <motion.div
                whileHover={{ x: 2 }}
                className={`
                  relative flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-all duration-200 group
                  ${isActive
                    ? 'bg-indigo-500/20 text-white'
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                  }
                `}
              >
                {/* Active indicator bar */}
                {isActive && (
                  <motion.div
                    layoutId={isMobile ? 'mobile-active-indicator' : 'active-indicator'}
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 bg-indigo-400 rounded-full shadow-[0_0_8px_rgba(99,102,241,0.8)]"
                  />
                )}

                <span className={`flex-shrink-0 ${isActive ? 'text-indigo-400' : ''}`}>
                  {item.icon}
                </span>

                {(!collapsed || isMobile) && (
                  <motion.span
                    initial={false}
                    className="text-sm font-medium whitespace-nowrap overflow-hidden"
                  >
                    {item.label}
                  </motion.span>
                )}

                {/* Tooltip when collapsed */}
                {collapsed && !isMobile && (
                  <div className="absolute left-full ml-3 px-2 py-1 bg-slate-800 border border-white/10 rounded-md text-xs text-white whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 shadow-xl">
                    {item.label}
                  </div>
                )}
              </motion.div>
            </Link>
          );
        })}
      </nav>

      {/* User Profile */}
      <div className="border-t border-white/10 p-3 flex-shrink-0">
        <div className={`flex items-center gap-3 ${collapsed && !isMobile ? 'justify-center' : ''}`}>
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center flex-shrink-0 text-white text-sm font-semibold shadow-md">
            {user?.fullName ? user.fullName.charAt(0).toUpperCase() : 'U'}
          </div>
          {(!collapsed || isMobile) && (
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-white truncate">{user?.fullName || 'User'}</p>
              <p className="text-xs text-slate-400 truncate">{user?.email || 'user@example.com'}</p>
            </div>
          )}
          {(!collapsed || isMobile) && (
            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-red-400 transition-colors flex-shrink-0"
              title="Sign out"
            >
              <LogOut size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-slate-950 text-white overflow-hidden">
      {/* Desktop Sidebar */}
      <motion.aside
        animate={{ width: sidebarW }}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
        className="hidden lg:flex flex-col fixed left-0 top-0 bottom-0 z-30 overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, rgba(15,15,30,0.95) 0%, rgba(10,10,25,0.98) 100%)',
          backdropFilter: 'blur(20px)',
          borderRight: '1px solid rgba(255,255,255,0.08)',
          boxShadow: '4px 0 24px rgba(0,0,0,0.4)',
        }}
      >
        <SidebarContent />
      </motion.aside>

      {/* Mobile Drawer Overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
              className="lg:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
            />
            <motion.aside
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ duration: 0.25, ease: 'easeInOut' }}
              className="lg:hidden fixed left-0 top-0 bottom-0 w-64 z-50 flex flex-col"
              style={{
                background: 'linear-gradient(180deg, rgba(15,15,30,0.98) 0%, rgba(10,10,25,0.99) 100%)',
                backdropFilter: 'blur(20px)',
                borderRight: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <button
                onClick={() => setMobileOpen(false)}
                className="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors z-10"
              >
                <X size={20} />
              </button>
              <SidebarContent isMobile />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Main Content */}
      <motion.div
        animate={{ marginLeft: sidebarW }}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
        className="hidden lg:flex flex-col flex-1 min-w-0"
      >
        {/* Top Header */}
        <header
          className="flex items-center h-16 px-6 flex-shrink-0 sticky top-0 z-20"
          style={{
            background: 'rgba(10,10,25,0.8)',
            backdropFilter: 'blur(16px)',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          {/* Page Title */}
          <h1 className="text-lg font-semibold text-white">
            {getPageTitle(pathname)}
          </h1>

          {/* Right Side */}
          <div className="ml-auto flex items-center gap-3">
            {/* Search */}
            <div className="relative hidden md:block">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search..."
                className="bg-white/5 border border-white/10 rounded-lg pl-9 pr-4 py-1.5 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 focus:bg-white/8 transition-all w-48 focus:w-64"
              />
            </div>

            {/* Notifications */}
            <div className="relative" onClick={(e) => { e.stopPropagation(); setNotifOpen((o) => !o); }}>
              <button className="relative p-2 text-slate-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors">
                <Bell size={18} />
                <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-indigo-500 rounded-full shadow-[0_0_6px_rgba(99,102,241,0.8)]" />
              </button>
              <AnimatePresence>
                {notifOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.95 }}
                    className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-white/10 shadow-2xl overflow-hidden z-50"
                    style={{ background: 'rgba(18,18,40,0.97)', backdropFilter: 'blur(20px)' }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="px-4 py-3 border-b border-white/10">
                      <p className="text-sm font-semibold text-white">Notifications</p>
                    </div>
                    {[
                      { msg: 'New audit completed for domain.com', time: '2m ago', dot: 'bg-indigo-500' },
                      { msg: '3 new leads discovered', time: '15m ago', dot: 'bg-emerald-500' },
                      { msg: 'Analytics report ready', time: '1h ago', dot: 'bg-purple-500' },
                    ].map((n, i) => (
                      <div key={i} className="flex items-start gap-3 px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer">
                        <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${n.dot}`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-slate-300">{n.msg}</p>
                          <p className="text-xs text-slate-500 mt-0.5">{n.time}</p>
                        </div>
                      </div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* User Menu */}
            <div
              className="relative"
              onClick={(e) => { e.stopPropagation(); setUserMenuOpen((o) => !o); }}
            >
              <button className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-white/5 transition-colors">
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-xs font-semibold">
                  {user?.fullName ? user.fullName.charAt(0).toUpperCase() : 'U'}
                </div>
                <span className="text-sm text-slate-300 hidden md:block">{user?.fullName || 'User'}</span>
                <ChevronDown size={14} className="text-slate-400" />
              </button>
              <AnimatePresence>
                {userMenuOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.95 }}
                    className="absolute right-0 top-full mt-2 w-52 rounded-xl border border-white/10 shadow-2xl overflow-hidden z-50"
                    style={{ background: 'rgba(18,18,40,0.97)', backdropFilter: 'blur(20px)' }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="px-4 py-3 border-b border-white/10">
                      <p className="text-sm font-medium text-white">{user?.fullName || 'User'}</p>
                      <p className="text-xs text-slate-400 mt-0.5">{user?.email}</p>
                    </div>
                    <Link href="/dashboard/settings">
                      <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-white/5 transition-colors cursor-pointer text-slate-300 hover:text-white text-sm">
                        <User size={15} />
                        Profile
                      </div>
                    </Link>
                    <Link href="/dashboard/settings">
                      <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-white/5 transition-colors cursor-pointer text-slate-300 hover:text-white text-sm">
                        <Settings size={15} />
                        Settings
                      </div>
                    </Link>
                    <div className="border-t border-white/10">
                      <button
                        onClick={handleLogout}
                        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-red-500/10 transition-colors text-slate-300 hover:text-red-400 text-sm"
                      >
                        <LogOut size={15} />
                        Sign out
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto">
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="h-full"
          >
            {children}
          </motion.div>
        </main>
      </motion.div>

      {/* Mobile layout (no margin-left animation) */}
      <div className="lg:hidden flex flex-col flex-1 min-w-0">
        <header
          className="flex items-center h-16 px-4 flex-shrink-0 sticky top-0 z-20"
          style={{
            background: 'rgba(10,10,25,0.9)',
            backdropFilter: 'blur(16px)',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 text-slate-400 hover:text-white transition-colors"
          >
            <Menu size={20} />
          </button>
          <h1 className="ml-3 text-base font-semibold text-white">{getPageTitle(pathname)}</h1>
          <div className="ml-auto flex items-center gap-2">
            <button className="relative p-2 text-slate-400 hover:text-white rounded-lg transition-colors">
              <Bell size={18} />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-indigo-500 rounded-full" />
            </button>
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-xs font-semibold">
              {user?.fullName ? user.fullName.charAt(0).toUpperCase() : 'U'}
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="h-full"
          >
            {children}
          </motion.div>
        </main>
      </div>
    </div>
  );
}
