'use client';

import React, { useState, useMemo } from 'react';
import Link from 'next/link';

// Build WhatsApp URL. US/Canada (+1) business numbers are almost never on WhatsApp
// (they're landlines). For all other countries, build the link.
function toWhatsAppUrl(phone: string | null | undefined, text: string): string | null {
  if (!phone) return null;
  const digits = phone.replace(/\D/g, '');
  if (digits.length < 7) return null;
  // Skip +1 US/Canada — business landlines, not on WhatsApp
  if (digits.startsWith('1') && digits.length === 11) return null;
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
}
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { discoveryApi, businessesApi, exportApi, outreachApi, crmApi } from '@/lib/api';
import type { DiscoveryJobRaw, BusinessRaw, DiscoveryJobCreatePayload, DealRaw } from '@/lib/api';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Plus,
  Globe,
  Globe2,
  MapPin,
  Building2,
  LayoutGrid,
  Table2,
  RefreshCw,
  Trash2,
  Eye,
  Play,
  X,
  ChevronDown,
  Calendar,
  ExternalLink,
  CheckCircle,
  AlertCircle,
  Clock,
  ScanSearch,
  Filter,
  MoreHorizontal,
  TrendingUp,
  Briefcase,
  Phone,
  Mail,
  Link2,
  Upload,
  FileText,
  Download,
  Copy,
  Check,
  Zap,
  Sparkles,
  Send,
  CheckCircle2,
  ArrowRight,
  MessageCircle,
  Instagram,
  ShieldCheck,
  ChevronRight,
  ChevronLeft,
  Bot,
} from 'lucide-react';
import GlassCard from '@/components/ui/GlassCard';
import Badge from '@/components/ui/Badge';
import StatCard from '@/components/ui/StatCard';
import ProgressBar from '@/components/ui/ProgressBar';
import ScoreRing from '@/components/ui/ScoreRing';

// ─── Types ────────────────────────────────────────────────────────────────────

type JobStatus = 'completed' | 'running' | 'failed' | 'queued' | 'pending' | 'cancelled' | 'paused';
type ViewMode = 'grid' | 'table';

interface DiscoveryJob {
  id: string;
  name: string;
  sources: string[];
  status: JobStatus;
  progress: number;
  found: number;
  started: string;
  duration: string;
  industry: string;
  country: string;
}

interface Business {
  id: string;
  name: string;
  industry: string;
  city: string;
  country: string;
  hasWebsite: boolean;
  website?: string;
  phone?: string;
  whatsapp?: string;
  email?: string;
  instagramUrl?: string;
  facebookUrl?: string;
  description?: string;
  opportunityScore: number;
  source: string;
  discoveredAt: string;
  jobId: string;
}

// ─── Mappers ──────────────────────────────────────────────────────────────────

function rawToJob(j: DiscoveryJobRaw): DiscoveryJob {
  const cfg = (j.config ?? {}) as Record<string, unknown>;
  const sources = Array.isArray(cfg.sources) ? (cfg.sources as string[]) : [];
  let duration = '—';
  if (j.started_at && j.completed_at) {
    const ms = new Date(j.completed_at).getTime() - new Date(j.started_at).getTime();
    const mins = Math.floor(ms / 60000);
    const secs = Math.floor((ms % 60000) / 1000);
    duration = `${mins}m ${secs}s`;
  }
  return {
    id: j.id,
    name: j.name,
    sources,
    status: (j.status as JobStatus) ?? 'queued',
    progress: j.total_processed > 0 && j.total_found > 0
      ? Math.round((j.total_processed / j.total_found) * 100)
      : j.status === 'completed' ? 100 : 0,
    found: j.total_found,
    started: j.started_at ? j.started_at.slice(0, 16).replace('T', ' ') : '—',
    duration,
    industry: String(cfg.industry ?? ''),
    country: String(cfg.country ?? ''),
  };
}

function rawToBusiness(b: BusinessRaw): Business {
  const actualHasWebsite = Boolean(b.has_website && b.website_url && b.website_url.trim());
  return {
    id: b.id,
    name: b.name,
    industry: b.industry ?? b.category ?? '',
    city: b.city ?? '',
    country: b.country ?? '',
    hasWebsite: actualHasWebsite,
    website: actualHasWebsite ? (b.website_url ?? undefined) : undefined,
    phone: b.phone ?? undefined,
    whatsapp: b.whatsapp ?? undefined,
    email: b.email ?? undefined,
    instagramUrl: b.instagram_url ?? undefined,
    facebookUrl: b.facebook_url ?? undefined,
    description: b.description ?? undefined,
    opportunityScore: b.opportunity_score ?? 0,
    source: b.source ?? '',
    discoveredAt: b.discovered_at ? b.discovered_at.slice(0, 10) : b.created_at.slice(0, 10),
    jobId: '',
  };
}

const INDUSTRIES = ['All Industries', 'Retail', 'Food & Beverage', 'Healthcare', 'Technology', 'Automotive', 'Wellness', 'Home Services'];
const COUNTRIES = [
  'All Countries',
  'United Arab Emirates',
  'Saudi Arabia',
  'Qatar',
  'Kuwait',
  'Bahrain',
  'Oman',
  'Pakistan',
  'United Kingdom',
  'United States',
  'Canada',
  'Australia',
  'Germany',
  'France',
  'India',
];

// ─── Dropdown data for new job modal ─────────────────────────────────────────

const KEYWORD_PRESETS = [
  { group: 'Food & Drink', items: ['Restaurants', 'Cafes', 'Pizza Shops', 'Bakeries', 'Bars & Pubs', 'Fast Food', 'Food Trucks', 'Ice Cream Shops', 'Sushi Restaurants', 'Indian Restaurants'] },
  { group: 'Health & Beauty', items: ['Hair Salons', 'Barbershops', 'Nail Salons', 'Spas', 'Gyms', 'Yoga Studios', 'Dental Clinics', 'Medical Clinics', 'Pharmacies', 'Opticians'] },
  { group: 'Home Services', items: ['Plumbers', 'Electricians', 'Cleaning Services', 'Landscaping', 'Roofing', 'HVAC', 'Painters', 'Locksmiths', 'Pest Control', 'Pool Services'] },
  { group: 'Retail', items: ['Clothing Stores', 'Shoe Stores', 'Jewelry Stores', 'Electronics Stores', 'Pet Shops', 'Toy Stores', 'Book Stores', 'Supermarkets', 'Flower Shops'] },
  { group: 'Professional', items: ['Law Firms', 'Accounting Firms', 'Real Estate Agencies', 'Insurance Agencies', 'Marketing Agencies', 'IT Services', 'Consultants', 'Architects'] },
  { group: 'Automotive', items: ['Car Dealerships', 'Auto Repair Shops', 'Car Wash', 'Tire Shops', 'Auto Parts Stores', 'Towing Services'] },
  { group: 'Education', items: ['Tutoring Centers', 'Driving Schools', 'Music Schools', 'Martial Arts Schools', 'Dance Studios', 'Preschools', 'Language Schools'] },
  { group: 'Hospitality', items: ['Hotels', 'Motels', 'B&Bs', 'Event Venues', 'Catering Services', 'Wedding Planners', 'Travel Agencies'] },
];

const CITY_PRESETS = [
  { group: 'United Arab Emirates', items: ['Dubai', 'Abu Dhabi', 'Sharjah', 'Ajman', 'Ras Al Khaimah', 'Al Ain', 'Fujairah'] },
  { group: 'Saudi Arabia', items: ['Riyadh', 'Jeddah', 'Mecca', 'Medina', 'Dammam', 'Khobar', 'Tabuk', 'Taif'] },
  { group: 'Qatar', items: ['Doha', 'Al Rayyan', 'Al Wakrah', 'Al Khor'] },
  { group: 'Kuwait', items: ['Kuwait City', 'Salmiya', 'Hawally', 'Al Ahmadi'] },
  { group: 'Bahrain', items: ['Manama', 'Riffa', 'Muharraq'] },
  { group: 'Oman', items: ['Muscat', 'Salalah', 'Sohar'] },
  { group: 'Pakistan', items: ['Karachi', 'Lahore', 'Islamabad', 'Rawalpindi', 'Faisalabad', 'Multan', 'Peshawar', 'Quetta', 'Sialkot', 'Gujranwala'] },
  { group: 'United Kingdom', items: ['London', 'Birmingham', 'Manchester', 'Glasgow', 'Leeds', 'Liverpool', 'Edinburgh', 'Bristol', 'Sheffield', 'Cardiff'] },
  { group: 'United States', items: ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'San Jose', 'Austin', 'Jacksonville', 'Miami', 'Seattle', 'Denver', 'Nashville', 'Las Vegas', 'Portland', 'Boston', 'Detroit'] },
  { group: 'Australia', items: ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide', 'Gold Coast', 'Canberra', 'Hobart', 'Darwin'] },
  { group: 'Canada', items: ['Toronto', 'Montreal', 'Vancouver', 'Calgary', 'Edmonton', 'Ottawa', 'Winnipeg', 'Quebec City', 'Hamilton'] },
  { group: 'Germany', items: ['Berlin', 'Hamburg', 'Munich', 'Cologne', 'Frankfurt', 'Stuttgart', 'Düsseldorf', 'Leipzig'] },
  { group: 'India', items: ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai', 'Kolkata', 'Pune', 'Ahmedabad', 'Jaipur', 'Surat'] },
];

const COUNTRY_PRESETS = [
  { group: 'Middle East & Gulf', items: ['United Arab Emirates', 'Saudi Arabia', 'Qatar', 'Kuwait', 'Bahrain', 'Oman', 'Egypt', 'Jordan'] },
  { group: 'South Asia', items: ['Pakistan', 'India', 'Bangladesh', 'Sri Lanka', 'Nepal'] },
  { group: 'Europe & UK', items: ['United Kingdom', 'Germany', 'France', 'Spain', 'Italy', 'Netherlands', 'Ireland', 'Switzerland'] },
  { group: 'North America', items: ['United States', 'Canada', 'Mexico'] },
  { group: 'Asia Pacific', items: ['Australia', 'New Zealand', 'Singapore', 'Malaysia', 'Japan'] },
];

const INDUSTRY_PRESETS = [
  { group: 'Food & Hospitality', items: ['Restaurant', 'Cafe', 'Bar & Nightclub', 'Hotel', 'Catering', 'Bakery', 'Food Truck'] },
  { group: 'Health & Wellness', items: ['Medical Clinic', 'Dental', 'Pharmacy', 'Gym & Fitness', 'Yoga Studio', 'Mental Health', 'Veterinary'] },
  { group: 'Beauty & Personal Care', items: ['Hair Salon', 'Barbershop', 'Nail Salon', 'Spa & Massage', 'Cosmetics'] },
  { group: 'Home & Trade', items: ['Plumbing', 'Electrical', 'Cleaning', 'Landscaping', 'Construction', 'HVAC', 'Roofing', 'Interior Design'] },
  { group: 'Retail', items: ['Clothing', 'Electronics', 'Furniture', 'Jewelry', 'Sports & Outdoors', 'Auto Parts', 'Pet Store'] },
  { group: 'Professional', items: ['Law', 'Accounting', 'Real Estate', 'Insurance', 'Marketing Agency', 'IT Services', 'Consulting'] },
  { group: 'Automotive', items: ['Car Dealership', 'Auto Repair', 'Car Wash', 'Tire & Wheel'] },
  { group: 'Education', items: ['Tutoring', 'Driving School', 'Music School', 'Dance Studio', 'Martial Arts', 'Language School'] },
];

const MAX_RESULTS_OPTIONS = [
  { label: '10 results (quick test)', value: 10 },
  { label: '25 results', value: 25 },
  { label: '50 results', value: 50 },
  { label: '100 results (recommended)', value: 100 },
  { label: '250 results', value: 250 },
  { label: '500 results', value: 500 },
  { label: '1000 results (slow)', value: 1000 },
];

// ─── Combobox component ───────────────────────────────────────────────────────

interface ComboBoxProps {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  groups: { group: string; items: string[] }[];
  icon?: React.ReactNode;
  allowCustom?: boolean;
}

function ComboBox({ value, onChange, placeholder, groups, icon, allowCustom = true }: ComboBoxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const filtered = query.trim()
    ? groups.map(g => ({ group: g.group, items: g.items.filter(i => i.toLowerCase().includes(query.toLowerCase())) })).filter(g => g.items.length > 0)
    : groups;

  const totalItems = filtered.reduce((n, g) => n + g.items.length, 0);

  function select(val: string) {
    onChange(val);
    setQuery('');
    setOpen(false);
  }

  return (
    <div ref={ref} className="relative">
      <div
        className="flex items-center gap-2 w-full px-3 py-2 rounded-lg border border-white/10 bg-white/5 text-sm text-slate-300 cursor-text focus-within:border-indigo-500/50 transition-colors"
        onClick={() => setOpen(true)}
      >
        {icon && <span className="text-slate-400 flex-shrink-0">{icon}</span>}
        <input
          type="text"
          value={open ? query : value}
          onChange={e => { setQuery(e.target.value); if (allowCustom) onChange(e.target.value); }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className="flex-1 bg-transparent outline-none text-slate-300 placeholder-slate-500 min-w-0"
        />
        {value && !open && (
          <button onClick={e => { e.stopPropagation(); onChange(''); setQuery(''); }} className="text-slate-500 hover:text-slate-300 flex-shrink-0">
            <X size={13} />
          </button>
        )}
        <ChevronDown size={13} className={`text-slate-400 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </div>

      {open && (
        <div
          className="absolute z-50 top-full mt-1 left-0 right-0 rounded-xl overflow-hidden shadow-2xl"
          style={{ background: 'rgba(14,14,32,0.99)', border: '1px solid rgba(255,255,255,0.12)', maxHeight: '280px', overflowY: 'auto' }}
        >
          {totalItems === 0 && allowCustom && query ? (
            <button
              className="w-full px-4 py-3 text-sm text-left text-indigo-400 hover:bg-indigo-500/10 transition-colors flex items-center gap-2"
              onClick={() => select(query)}
            >
              <Plus size={13} /> Use &quot;{query}&quot;
            </button>
          ) : null}
          {filtered.map(g => (
            <div key={g.group}>
              <div className="px-3 py-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wider sticky top-0" style={{ background: 'rgba(14,14,32,0.98)' }}>
                {g.group}
              </div>
              {g.items.map(item => (
                <button
                  key={item}
                  className={`w-full px-4 py-2 text-sm text-left transition-colors flex items-center gap-2 ${value === item ? 'bg-indigo-500/15 text-indigo-300' : 'text-slate-300 hover:bg-white/5 hover:text-white'}`}
                  onClick={() => select(item)}
                >
                  {value === item && <CheckCircle size={12} className="text-indigo-400 flex-shrink-0" />}
                  {item}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function statusBadge(status: JobStatus) {
  switch (status) {
    case 'completed':  return <Badge variant="success" dot>Completed</Badge>;
    case 'running':    return <Badge variant="info" dot>Running</Badge>;
    case 'failed':     return <Badge variant="danger" dot>Failed</Badge>;
    case 'cancelled':  return <Badge variant="slate" dot>Cancelled</Badge>;
    case 'paused':     return <Badge variant="warning" dot>Paused</Badge>;
    case 'queued':
    case 'pending':
    default:           return <Badge variant="slate" dot>Pending</Badge>;
  }
}

function industryColor(industry: string): string {
  const map: Record<string, string> = {
    Retail: 'default',
    'Food & Beverage': 'warning',
    Healthcare: 'success',
    Technology: 'info',
    Automotive: 'purple',
    Wellness: 'success',
    'Home Services': 'warning',
  };
  return map[industry] || 'slate';
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SelectDropdown({
  value,
  onChange,
  options,
  icon,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  icon?: React.ReactNode;
}) {
  return (
    <div className="relative">
      {icon && (
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
          {icon}
        </span>
      )}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`appearance-none rounded-lg border border-white/10 bg-white/5 text-sm text-slate-300 pr-8 py-2 focus:outline-none focus:border-indigo-500/50 transition-colors cursor-pointer ${icon ? 'pl-9' : 'pl-3'}`}
      >
        {options.map((o) => (
          <option key={o} value={o} className="bg-slate-900">
            {o}
          </option>
        ))}
      </select>
      <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
    </div>
  );
}

function SourceBadge({ source }: { source: string }) {
  const s = (source || '').toLowerCase();
  if (s === 'instagram') {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-pink-500/15 text-pink-300 border border-pink-500/30">📸 Instagram</span>;
  }
  if (s === 'facebook') {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/15 text-blue-300 border border-blue-500/30">👥 Facebook</span>;
  }
  if (s === 'reddit') {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-orange-500/15 text-orange-300 border border-orange-500/30">💬 Reddit Lead</span>;
  }
  if (s === 'freelance' || s === 'freelancer' || s === 'upwork' || s === 'fiverr') {
    const label = s === 'upwork' ? '💼 Upwork' : s === 'fiverr' ? '💼 Fiverr' : s === 'freelancer' ? '💼 Freelancer' : '💼 Freelance';
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">{label}</span>;
  }
  if (s.includes('ecommerce') || s.includes('daraz')) {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">🛍️ E-Commerce</span>;
  }
  if (s.includes('google')) {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30">🗺️ Google</span>;
  }
  return <span className="text-slate-500 text-xs capitalize">{source}</span>;
}

function BusinessCard({
  business,
  onClick,
  isContacted,
  isSelected,
  onToggleSelect,
  onDelete,
  onQuickWhatsApp,
  onQuickInstagram,
}: {
  business: Business;
  onClick: () => void;
  isContacted?: boolean;
  isSelected?: boolean;
  onToggleSelect?: (e: React.MouseEvent) => void;
  onDelete?: (e: React.MouseEvent) => void;
  onQuickWhatsApp?: (e: React.MouseEvent) => void;
  onQuickInstagram?: (e: React.MouseEvent) => void;
}) {
  const hasWhatsApp = Boolean(business.phone && !business.phone.startsWith('+1'));
  const isReddit = business.source === 'reddit';
  const isFreelance = ['freelance', 'upwork', 'freelancer', 'fiverr'].includes(business.source?.toLowerCase());
  const hasEmail = Boolean(business.email);

  return (
    <motion.div
      whileHover={{ y: -4, boxShadow: '0 24px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(99,102,241,0.25)' }}
      transition={{ duration: 0.2 }}
      onClick={onClick}
      className={`relative rounded-xl overflow-hidden cursor-pointer group flex flex-col justify-between ${
        isSelected ? 'ring-2 ring-indigo-500 bg-indigo-950/20' : ''
      }`}
      style={{
        background: isSelected ? 'rgba(30,27,75,0.7)' : 'rgba(14,14,32,0.6)',
        backdropFilter: 'blur(16px)',
        border: isSelected ? '1px solid rgba(99,102,241,0.5)' : '1px solid rgba(255,255,255,0.07)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      }}
    >
      {/* Top accent */}
      <div
        className="h-0.5 w-full"
        style={{ background: isSelected ? 'linear-gradient(90deg, #6366f1, #a855f7)' : 'linear-gradient(90deg, #6366f1, #a855f7, #ec4899)' }}
      />

      <div className="p-4 flex-1 flex flex-col justify-between">
        <div>
          {/* Header row */}
          <div className="flex items-start justify-between gap-2 mb-3">
            <div className="flex items-start gap-2.5 min-w-0 flex-1">
              {onToggleSelect && (
                <div className="pt-0.5" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={Boolean(isSelected)}
                    onChange={() => {}}
                    onClick={onToggleSelect}
                    className="w-4 h-4 rounded border-white/20 bg-white/10 accent-indigo-500 cursor-pointer"
                    title="Select lead"
                  />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-white text-sm leading-snug truncate group-hover:text-indigo-300 transition-colors">
                  {business.name}
                </p>
                <div className="flex items-center gap-1 mt-1 text-xs text-slate-400">
                  <MapPin size={11} />
                  <span className="truncate">
                    {business.city ? `${business.city}, ` : ''}{business.country || 'Global'}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <ScoreRing score={business.opportunityScore} size={44} strokeWidth={4} showValue animate={false} />
              {onDelete && (
                <button
                  onClick={onDelete}
                  title="Delete lead"
                  className="p-1 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100 cursor-pointer"
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          </div>

          {/* Industry & Source badges */}
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <Badge variant={industryColor(business.industry) as any} size="sm">
              {business.industry || 'General'}
            </Badge>
            <SourceBadge source={business.source} />
          </div>
        </div>

        <div>
          {/* Website status & Verified Contact Badges */}
          <div className="flex items-center justify-between text-xs pt-1 border-t border-white/5 gap-1">
            <div className="flex items-center gap-1.5 min-w-0">
              {isReddit ? (
                <span className="flex items-center gap-1 text-orange-400 font-medium">
                  <Briefcase size={12} />
                  Hiring Client
                </span>
              ) : isFreelance ? (
                <span className="flex items-center gap-1 text-emerald-400 font-medium">
                  <Briefcase size={12} />
                  Hiring Project
                </span>
              ) : business.hasWebsite ? (
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle size={12} />
                  Has website
                </span>
              ) : (
                <span className="flex items-center gap-1 text-amber-400 font-medium">
                  <AlertCircle size={12} />
                  No website
                </span>
              )}
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              {isFreelance && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-300 bg-emerald-500/15 px-1.5 py-0.5 rounded border border-emerald-500/30">
                  💼 Job Post ✓
                </span>
              )}
              {isReddit && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-orange-400 bg-orange-500/10 px-1.5 py-0.5 rounded border border-orange-500/20">
                  💬 Client DM ✓
                </span>
              )}
              {hasWhatsApp && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                  WhatsApp ✓
                </span>
              )}
              {business.source === 'instagram' && !hasWhatsApp && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-pink-400 bg-pink-500/10 px-1.5 py-0.5 rounded border border-pink-500/20">
                  📸 Insta DM ✓
                </span>
              )}
              {business.source === 'facebook' && !hasWhatsApp && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded border border-blue-500/20">
                  👥 FB Msg ✓
                </span>
              )}
              {hasEmail && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded border border-blue-500/20">
                  Email ✓
                </span>
              )}
            </div>
          </div>

          {/* 1-Click Outreach Action Bar for No-Website & Freelance Leads */}
          {!business.hasWebsite && (
            <div
              className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between gap-1.5"
              onClick={(e) => e.stopPropagation()}
            >
              {isContacted ? (
                <div className="w-full flex items-center justify-center gap-1.5 py-1 px-2 rounded-lg text-[11px] font-medium text-purple-300 bg-purple-500/15 border border-purple-500/30">
                  <CheckCircle2 size={12} className="text-purple-400" />
                  <span>Contacted in CRM</span>
                </div>
              ) : isFreelance ? (
                <button
                  onClick={onClick}
                  className="w-full flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-[11px] font-semibold text-white bg-emerald-600 hover:bg-emerald-500 transition-all shadow-sm"
                  title="View Tailored Proposal & Open Job"
                >
                  <Briefcase size={11} />
                  <span>💼 View Job &amp; Proposal</span>
                </button>
              ) : (
                <>
                  {hasWhatsApp && onQuickWhatsApp ? (
                    <button
                      onClick={onQuickWhatsApp}
                      className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded-lg text-[11px] font-semibold text-white bg-emerald-600 hover:bg-emerald-500 transition-all shadow-sm"
                      title="1-Click WhatsApp Pitch & Move Deal to Contacted"
                    >
                      <Phone size={10} />
                      <span>WA Pitch</span>
                    </button>
                  ) : null}
                  {(business.source === 'instagram' || business.instagramUrl) && onQuickInstagram ? (
                    <button
                      onClick={onQuickInstagram}
                      className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded-lg text-[11px] font-semibold text-white transition-all shadow-sm"
                      style={{ background: 'linear-gradient(135deg, #f09433, #e6683c 25%, #dc2743 50%, #cc2366 75%, #bc1888 100%)' }}
                      title="Copy Pitch, Open Instagram & Move Deal to Contacted"
                    >
                      <Instagram size={10} />
                      <span>DM Pitch</span>
                    </button>
                  ) : null}
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Hover overlay */}
      <div className="absolute inset-0 bg-indigo-500/0 group-hover:bg-indigo-500/5 transition-colors pointer-events-none" />
    </motion.div>
  );
}

function BusinessDetailModal({
  business,
  onClose,
  onTriggerAudit,
  onDelete,
}: {
  business: Business;
  onClose: () => void;
  onTriggerAudit: (b: Business) => void;
  onDelete?: (b: Business) => void;
}) {
  const { data: raw } = useQuery({
    queryKey: ['business-raw', business.id],
    queryFn: () => businessesApi.get(business.id),
  });

  const queryClient = useQueryClient();
  const { data: generatedEmail, mutate: generateEmail, isPending: generatingEmail, reset: resetEmail } = useMutation({
    mutationFn: () => outreachApi.generateEmail({ business_id: business.id, sender_name: 'Our Team', template_type: 'initial_outreach', include_audit: true }),
  });

  const { mutate: enrichContacts, isPending: enriching, isSuccess: enriched } = useMutation({
    mutationFn: () => businessesApi.enrichContacts(business.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['business-raw', business.id] });
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
    },
  });

  const [sendStatus, setSendStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [sendMsg, setSendMsg] = useState('');

  const handleSendDirect = async () => {
    if (!generatedEmail) return;
    const toEmail = raw?.email ?? business.email ?? '';
    if (!toEmail) { setSendStatus('error'); setSendMsg('No email address for this business'); return; }
    setSendStatus('sending');
    try {
      await outreachApi.sendEmail({
        business_id: business.id,
        to_email: toEmail,
        subject: generatedEmail.subject,
        body_html: generatedEmail.body_html,
        body_text: generatedEmail.body_text,
      });
      setSendStatus('sent');
      setSendMsg(`Sent to ${toEmail}`);
    } catch (err: unknown) {
      setSendStatus('error');
      const msg = (err as { message?: string })?.message ?? 'Failed to send';
      setSendMsg(msg.includes('SMTP not configured') ? 'SMTP not configured — go to Settings → Email / SMTP' : msg);
    }
  };

  const social = (raw?.social_profiles ?? {}) as Record<string, string>;
  const phone = raw?.phone ?? business.phone ?? null;
  const email = raw?.email ?? business.email ?? null;
  const address = raw?.address ?? null;
  const website = raw?.website_url ?? business.website ?? null;
  const tags: string[] = raw?.tags ?? [];
  const meta = (raw?.metadata_ ?? raw?.metadata ?? {}) as Record<string, any>;
  const rawSource = (meta?.raw_source ?? {}) as Record<string, any>;

  const instagramUrl = raw?.instagram_url || meta?.instagram_url || rawSource?.instagram_url || social?.instagram || null;
  const facebookUrl = raw?.facebook_url || meta?.facebook_url || rawSource?.facebook_url || social?.facebook || null;
  const redditUrl = meta?.reddit_url || rawSource?.reddit_url || (business.source === 'reddit' ? (raw?.website_url || business.website) : null);
  const discord = meta?.discord || rawSource?.discord || null;
  const subreddit = meta?.subreddit || rawSource?.subreddit || null;
  const budget = meta?.budget || rawSource?.budget || null;
  const techStack = meta?.tech_stack || rawSource?.tech_stack || null;
  const followers = meta?.followers || rawSource?.followers || null;
  const isReddit = business.source === 'reddit' || Boolean(redditUrl);

  const projectUrl = meta?.project_url || rawSource?.project_url || meta?.job_url || rawSource?.job_url || (['freelance', 'upwork', 'freelancer', 'fiverr'].includes(business.source?.toLowerCase()) ? (raw?.source_url || raw?.website_url || business.website) : null);
  const platform = meta?.platform || rawSource?.platform || (business.source === 'upwork' ? 'Upwork' : business.source === 'freelancer' ? 'Freelancer' : business.source === 'fiverr' ? 'Fiverr' : 'Freelance Platform');
  const isFreelance = ['freelance', 'upwork', 'freelancer', 'fiverr'].includes(business.source?.toLowerCase()) || Boolean(projectUrl);
  const isClientLead = isReddit || isFreelance;

  // Custom high-converting pitch hook
  const defaultRedditPitch = `Hi! Saw your hiring post on ${subreddit || 'Reddit'} regarding "${business.name.replace(/^Client\s*\[r\/\w+\]:\s*/i, '')}". I build fast, modern web applications & e-commerce systems and have completed similar projects on time and within budget. Would love to send over my portfolio or jump on a quick call!`;
  const defaultFreelancePitch = `Hi there! Saw your project "${business.name.replace(/^Client:\s*/i, '')}" on ${platform}.${budget ? ` I noticed your budget of ${budget} and can comfortably deliver within that range.` : ''}\n\nI specialize in building sleek, high-performing websites and e-commerce storefronts tailored to client goals. Here is how I would approach your project:\n1. Fast Scope & Design: Confirm design preferences, brand assets, and technical needs upfront.\n2. Mobile-First Development: Clean, modern layout optimized for fast load speeds, conversions, and SEO.\n3. Interactive Milestone Preview: Working preview within 48-72 hours to test and review.\n4. Launch & Handoff: Full testing, domain linking, and 30 days of complimentary post-launch support.\n\nWould love to discuss your timeline or share a quick live demo. When is a good time for a quick chat?`;
  const defaultSocialPitch = `Hi ${business.name}! Noticed you take customer orders via social channels/WhatsApp without an automated website storefront. We build modern, high-converting stores that connect directly with your WhatsApp. Can I show you a quick demo?`;
  const defaultWebPitch = `Hi ${business.name}! We help growing businesses optimize mobile page speed and double checkout conversion rates. Would love to share a free performance teardown.`;

  const customPitch = meta?.pitch || rawSource?.pitch || (
    isFreelance ? defaultFreelancePitch : (isReddit ? defaultRedditPitch : (!business.hasWebsite ? defaultSocialPitch : defaultWebPitch))
  );

  const [copiedPitch, setCopiedPitch] = useState(false);
  const handleCopyPitch = () => {
    navigator.clipboard.writeText(customPitch);
    setCopiedPitch(true);
    setTimeout(() => setCopiedPitch(false), 2500);
  };

  const handleLaunchOutreach = async (channel: string, url: string) => {
    window.open(url, '_blank');
    try {
      await discoveryApi.markContacted(business.id, channel);
      queryClient.invalidateQueries({ queryKey: ['crm', 'deals'] });
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
    } catch {}
  };

  // WhatsApp — only for non-US/Canada numbers (landlines won't work)
  const whatsappUrl = toWhatsAppUrl(phone, customPitch);

  // Gmail compose
  const gmailUrl = email
    ? `https://mail.google.com/mail/?view=cm&to=${encodeURIComponent(email)}&su=${encodeURIComponent(isReddit || isFreelance ? `Proposal / Application: ${business.name}` : `Growth Opportunity — ${business.name}`)}&body=${encodeURIComponent(customPitch)}`
    : null;

  const SOCIAL_MAP: Record<string, { color: string; label: string; base: string }> = {
    facebook:  { color: '#1877F2', label: 'Facebook',  base: 'https://facebook.com/' },
    instagram: { color: '#E1306C', label: 'Instagram', base: 'https://instagram.com/' },
    twitter:   { color: '#1DA1F2', label: 'Twitter/X', base: 'https://x.com/' },
    linkedin:  { color: '#0A66C2', label: 'LinkedIn',  base: 'https://linkedin.com/company/' },
    youtube:   { color: '#FF0000', label: 'YouTube',   base: 'https://youtube.com/' },
    tiktok:    { color: '#69C9D0', label: 'TikTok',    base: 'https://tiktok.com/@' },
    whatsapp:  { color: '#25D366', label: 'WhatsApp',  base: 'https://wa.me/' },
    snapchat:  { color: '#FFFC00', label: 'Snapchat',  base: 'https://snapchat.com/add/' },
  };

  return (
    <AnimatePresence>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Side Panel */}
      <motion.div
        initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 28, stiffness: 280 }}
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-lg overflow-y-auto"
        style={{ background: 'rgba(10,10,24,0.99)', borderLeft: '1px solid rgba(255,255,255,0.08)', boxShadow: '-24px 0 64px rgba(0,0,0,0.7)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="sticky top-0 z-10 px-5 py-4 flex items-start justify-between border-b border-white/10"
          style={{ background: 'rgba(10,10,24,0.97)', backdropFilter: 'blur(20px)' }}>
          <div className="flex-1 min-w-0 pr-3">
            <h2 className="text-lg font-bold text-white truncate">{business.name}</h2>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              <span className="flex items-center gap-1 text-xs text-slate-400"><MapPin size={11} />{business.city}{business.country ? `, ${business.country}` : ''}</span>
              <span className="text-slate-600">·</span>
              <Badge variant={industryColor(business.industry) as any} size="sm">{business.industry || 'Unknown'}</Badge>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors flex-shrink-0">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-5">

          {/* ── Score + Quick Stats ── */}
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center p-3 rounded-xl" style={{ background: 'rgba(99,102,241,0.10)', border: '1px solid rgba(99,102,241,0.2)' }}>
              <div className="text-2xl font-black text-indigo-300">{business.opportunityScore || '—'}</div>
              <div className="text-xs text-slate-500 mt-0.5">Opportunity</div>
            </div>
            <div className="text-center p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <div className={`text-sm font-bold mt-1 ${isFreelance ? 'text-emerald-400' : isReddit ? 'text-orange-400' : business.hasWebsite ? 'text-emerald-400' : 'text-amber-400'}`}>
                {isFreelance ? '💼 Project' : isReddit ? '💼 Client' : business.hasWebsite ? '✓ Yes' : '✗ No'}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">{isClientLead ? 'Type' : 'Website'}</div>
            </div>
            <div className="text-center p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <div className="text-xs font-bold text-slate-300 mt-1 capitalize">{platform || business.source || '—'}</div>
              <div className="text-xs text-slate-500 mt-0.5">{budget ? `Budget: ${budget}` : (techStack || followers ? (techStack ? `Tech: ${techStack}` : `${followers}`) : 'Source')}</div>
            </div>
          </div>

          {/* ── Direct Personalized Pitch Card ── */}
          <div className="rounded-xl overflow-hidden" style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(168,85,247,0.08))', border: '1px solid rgba(99,102,241,0.3)' }}>
            <div className="px-4 py-2.5 flex items-center justify-between border-b border-white/5" style={{ background: 'rgba(99,102,241,0.12)' }}>
              <span className="text-xs font-semibold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                ⚡ Tailored Outreach Pitch
              </span>
              <button
                onClick={handleCopyPitch}
                className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium text-white transition-all bg-indigo-600 hover:bg-indigo-500"
              >
                {copiedPitch ? <Check size={12} className="text-green-300" /> : <Copy size={12} />}
                {copiedPitch ? 'Copied!' : 'Copy Pitch'}
              </button>
            </div>
            <div className="p-4 space-y-3">
              <p className="text-xs text-slate-200 leading-relaxed font-sans bg-black/30 p-3 rounded-lg border border-white/5 whitespace-pre-line">
                &ldquo;{customPitch}&rdquo;
              </p>
              {/* 1-Click Multi-Channel Contact Row */}
              <div className="flex flex-wrap gap-2 pt-1">
                {isFreelance && projectUrl && (
                  <button
                    onClick={() => handleLaunchOutreach(platform || 'freelance', projectUrl)}
                    className="flex-1 min-w-[140px] flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-lg text-xs font-bold text-white transition-all hover:opacity-95 shadow-lg"
                    style={{ background: platform?.toLowerCase().includes('upwork') ? 'linear-gradient(135deg, #14a800, #108a00)' : platform?.toLowerCase().includes('fiverr') ? 'linear-gradient(135deg, #1dbf73, #19a463)' : 'linear-gradient(135deg, #007fed, #0060b2)' }}
                  >
                    💼 Open {platform} &amp; Apply
                  </button>
                )}
                {isReddit && redditUrl && (
                  <button
                    onClick={() => handleLaunchOutreach('reddit', redditUrl)}
                    className="flex-1 min-w-[140px] flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-lg text-xs font-bold text-white transition-all hover:opacity-95 shadow-lg"
                    style={{ background: '#FF4500' }}
                  >
                    💬 Message Client on Reddit
                  </button>
                )}
                {whatsappUrl && (
                  <button
                    onClick={() => handleLaunchOutreach('whatsapp', whatsappUrl)}
                    className="flex-1 min-w-[120px] flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold text-white transition-all hover:opacity-90"
                    style={{ background: '#25D366' }}
                  >
                    <Phone size={13} /> Open WhatsApp
                  </button>
                )}
                {instagramUrl && (
                  <button
                    onClick={() =>
                      handleLaunchOutreach(
                        'instagram',
                        instagramUrl.startsWith('http')
                          ? instagramUrl
                          : `https://instagram.com/${instagramUrl.replace('@', '')}`
                      )
                    }
                    className="flex-1 min-w-[120px] flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold text-white transition-all hover:opacity-90"
                    style={{ background: '#E1306C' }}
                  >
                    📸 DM on Instagram
                  </button>
                )}
                {facebookUrl && (
                  <button
                    onClick={() =>
                      handleLaunchOutreach(
                        'facebook',
                        facebookUrl.startsWith('http') ? facebookUrl : `https://facebook.com/${facebookUrl}`
                      )
                    }
                    className="flex-1 min-w-[120px] flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold text-white transition-all hover:opacity-90"
                    style={{ background: '#1877F2' }}
                  >
                    👥 Message on Facebook
                  </button>
                )}
                {email && gmailUrl && (
                  <button
                    onClick={() => handleLaunchOutreach('email', gmailUrl)}
                    className="flex-1 min-w-[120px] flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold text-white transition-all hover:opacity-90"
                    style={{ background: '#EA4335' }}
                  >
                    <Mail size={13} /> Gmail Client
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* ── Contact Actions ── */}
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
            <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
              <Phone size={13} className="text-slate-400" />
              <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                {isFreelance ? '💼 Client Project & Job Post' : isReddit ? 'Client Contact & Outreach' : 'Contact Details'}
              </span>
            </div>
            <div className="p-4 space-y-3">
              {isFreelance ? (
                <div className="space-y-3">
                  <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/25 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                        💼 Active {platform} Project
                      </span>
                      {budget && (
                        <span className="text-xs font-bold text-emerald-300 bg-emerald-500/20 px-2 py-0.5 rounded border border-emerald-500/30">
                          Budget: {budget}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      This client is actively hiring on <strong>{platform}</strong>. We have generated an AI-tailored winning proposal for you above. Copy your proposal with 1 click, open the job link below, and submit your bid!
                    </p>
                    {projectUrl && (
                      <a
                        href={projectUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-bold text-white transition-all hover:opacity-95 shadow-lg"
                        style={{ background: platform?.toLowerCase().includes('upwork') ? 'linear-gradient(135deg, #14a800, #108a00)' : platform?.toLowerCase().includes('fiverr') ? 'linear-gradient(135deg, #1dbf73, #19a463)' : 'linear-gradient(135deg, #007fed, #0060b2)' }}
                      >
                        <ExternalLink size={13} /> View Job on {platform} &amp; Submit Bid
                      </a>
                    )}
                  </div>

                  {email && (
                    <div className="flex items-center justify-between p-2.5 rounded-lg bg-black/40 border border-white/10 text-xs">
                      <span className="text-slate-300 flex items-center gap-1.5 truncate">
                        <Mail size={13} className="text-blue-400 flex-shrink-0" />
                        <span className="truncate">{email}</span>
                      </span>
                      <a
                        href={gmailUrl!}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-2.5 py-1 rounded text-xs font-semibold text-white bg-[#EA4335] hover:opacity-90 flex-shrink-0"
                      >
                        Email Client
                      </a>
                    </div>
                  )}
                </div>
              ) : isReddit ? (
                <div className="space-y-3">
                  <div className="p-3.5 rounded-xl bg-orange-500/10 border border-orange-500/25 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-orange-400 flex items-center gap-1.5">
                        💬 Verified Reddit Hiring Client
                      </span>
                      {budget && (
                        <span className="text-xs font-bold text-emerald-300 bg-emerald-500/20 px-2 py-0.5 rounded border border-emerald-500/30">
                          Budget: {budget}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      This lead was posted directly by an employer/founder on <strong>{subreddit || 'Reddit'}</strong> looking to hire for this project. Reach out to them via direct message or comment on their thread with your tailored proposal pitch.
                    </p>
                    {redditUrl && (
                      <a
                        href={redditUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-bold text-white transition-all hover:opacity-95 shadow-lg"
                        style={{ background: 'linear-gradient(135deg, #FF4500, #FF6A00)' }}
                      >
                        <ExternalLink size={13} /> Open Reddit Post &amp; Apply to Client
                      </a>
                    )}
                  </div>

                  {discord && (
                    <div className="flex items-center justify-between p-2.5 rounded-lg bg-black/40 border border-white/10 text-xs">
                      <span className="text-slate-300 flex items-center gap-1.5">
                        <strong className="text-[#5865F2]">Discord:</strong> {discord}
                      </span>
                      <button
                        onClick={() => navigator.clipboard.writeText(discord)}
                        className="text-xs text-indigo-400 hover:text-indigo-300 font-medium"
                      >
                        Copy Handle
                      </button>
                    </div>
                  )}

                  {email && (
                    <div className="flex items-center justify-between p-2.5 rounded-lg bg-black/40 border border-white/10 text-xs">
                      <span className="text-slate-300 flex items-center gap-1.5 truncate">
                        <Mail size={13} className="text-blue-400 flex-shrink-0" />
                        <span className="truncate">{email}</span>
                      </span>
                      <a
                        href={gmailUrl!}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-2.5 py-1 rounded text-xs font-semibold text-white bg-[#EA4335] hover:opacity-90 flex-shrink-0"
                      >
                        Email Client
                      </a>
                    </div>
                  )}
                </div>
              ) : (
                <>
                  {phone ? (
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 text-sm">
                        <Phone size={14} className="text-green-400 flex-shrink-0" />
                        <span className="text-slate-200 font-medium">{phone}</span>
                      </div>
                      {whatsappUrl ? (
                        <a
                          href={whatsappUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-all hover:opacity-90 flex-shrink-0"
                          style={{ background: '#25D366' }}
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                          WhatsApp
                        </a>
                      ) : (
                        <span className="text-xs text-slate-500 italic">Not on WhatsApp</span>
                      )}
                    </div>
                  ) : null}

                  {email ? (
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 text-sm min-w-0">
                        <Mail size={14} className="text-blue-400 flex-shrink-0" />
                        <span className="text-slate-200 font-medium truncate">{email}</span>
                      </div>
                      <a
                        href={gmailUrl!}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-all hover:opacity-90 flex-shrink-0"
                        style={{ background: '#EA4335' }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="white"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
                        Gmail
                      </a>
                    </div>
                  ) : null}

                  {instagramUrl && !phone && !email && (
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs text-slate-300">Instagram Profile Available</span>
                      <a
                        href={instagramUrl.startsWith('http') ? instagramUrl : `https://instagram.com/${instagramUrl.replace('@', '')}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-pink-600 hover:bg-pink-500"
                      >
                        📸 Open Instagram
                      </a>
                    </div>
                  )}

                  {facebookUrl && !phone && !email && (
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs text-slate-300">Facebook Page Available</span>
                      <a
                        href={facebookUrl.startsWith('http') ? facebookUrl : `https://facebook.com/${facebookUrl}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500"
                      >
                        👥 Open Facebook
                      </a>
                    </div>
                  )}

                  {!phone && !email && !instagramUrl && !facebookUrl && (
                    <p className="text-sm text-slate-500 italic">No contact info found for this business</p>
                  )}
                </>
              )}
            </div>
          </div>

          {/* ── Auto Email Generator ── */}
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(99,102,241,0.2)' }}>
            <div className="px-4 py-2.5 flex items-center justify-between" style={{ background: 'rgba(99,102,241,0.08)' }}>
              <div className="flex items-center gap-2">
                <Mail size={13} className="text-indigo-400" />
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Auto Email Outreach</span>
              </div>
              {generatedEmail && (
                <button onClick={() => resetEmail()} className="text-xs text-slate-500 hover:text-slate-300">Reset</button>
              )}
            </div>
            {!generatedEmail ? (
              <div className="p-4">
                <p className="text-xs text-slate-500 mb-3">AI generates a personalised outreach email using this business&apos;s audit data and industry.</p>
                <button
                  onClick={() => generateEmail()}
                  disabled={generatingEmail}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
                  style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)' }}
                >
                  {generatingEmail ? (
                    <><motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}><RefreshCw size={14} /></motion.div> Generating…</>
                  ) : (
                    <><Mail size={14} /> Generate Outreach Email</>
                  )}
                </button>
              </div>
            ) : (
              <div className="p-4 space-y-3">
                <div className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <p className="text-xs text-slate-500 mb-1">Subject</p>
                  <p className="text-sm font-semibold text-white">{generatedEmail.subject}</p>
                </div>
                <div className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <p className="text-xs text-slate-500 mb-2">Body</p>
                  <pre className="text-xs text-slate-300 whitespace-pre-wrap font-sans leading-relaxed max-h-40 overflow-y-auto">{generatedEmail.body_text}</pre>
                </div>
                {sendStatus !== 'idle' && (
                  <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium ${sendStatus === 'sent' ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20' : sendStatus === 'error' ? 'bg-red-500/10 text-red-300 border border-red-500/20' : 'bg-white/5 text-slate-400'}`}>
                    {sendStatus === 'sending' && <span className="animate-spin inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full" />}
                    {sendMsg || 'Sending…'}
                  </div>
                )}
                <div className="flex gap-2">
                  {email ? (
                    <>
                      <button
                        onClick={handleSendDirect}
                        disabled={sendStatus === 'sending' || sendStatus === 'sent'}
                        className="flex items-center justify-center gap-2 flex-1 py-2.5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
                        style={{ background: 'linear-gradient(135deg,#6366f1,#a855f7)' }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                        {sendStatus === 'sending' ? 'Sending…' : sendStatus === 'sent' ? 'Sent!' : 'Send Direct'}
                      </button>
                      <a
                        href={`https://mail.google.com/mail/?view=cm&to=${encodeURIComponent(email)}&su=${encodeURIComponent(generatedEmail.subject)}&body=${encodeURIComponent(generatedEmail.body_text)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-center gap-2 flex-1 py-2.5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90"
                        style={{ background: '#EA4335' }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="white"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
                        Gmail
                      </a>
                    </>
                  ) : toWhatsAppUrl(phone, generatedEmail.body_text.slice(0, 1000)) ? (
                    <a
                      href={toWhatsAppUrl(phone, generatedEmail.body_text.slice(0, 1000))!}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90"
                      style={{ background: '#25D366' }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                      Send via WhatsApp
                    </a>
                  ) : (
                    <p className="text-xs text-slate-500 text-center w-full py-2">No email or WhatsApp number found — click &quot;Fetch Email &amp; Phone&quot; below</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ── Business Details ── */}
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.07)' }}>
            <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
              <Building2 size={13} className="text-slate-400" />
              <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Business Details</span>
            </div>
            <div className="divide-y divide-white/5">
              {[
                { label: 'Address', value: address },
                { label: 'Website', value: website, link: website ? (website.startsWith('http') ? website : `https://${website}`) : null },
                { label: 'Industry', value: raw?.industry ?? business.industry },
                { label: 'Category', value: raw?.category ?? null },
                { label: 'Source', value: business.source },
                { label: 'Discovered', value: business.discoveredAt },
              ].filter(r => r.value).map(row => (
                <div key={row.label} className="flex items-center justify-between px-4 py-2.5 gap-3">
                  <span className="text-xs text-slate-500 flex-shrink-0 w-20">{row.label}</span>
                  {row.link ? (
                    <a href={row.link} target="_blank" rel="noopener noreferrer" className="text-xs font-medium text-emerald-400 hover:text-emerald-300 truncate flex items-center gap-1">
                      {row.value} <ExternalLink size={10} />
                    </a>
                  ) : (
                    <span className="text-xs font-medium text-slate-300 truncate text-right">{row.value}</span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* ── Social Media ── */}
          {Object.keys(social).length > 0 && (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.07)' }}>
              <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <Link2 size={13} className="text-slate-400" />
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Social Media</span>
              </div>
              <div className="p-4 flex flex-wrap gap-2">
                {Object.entries(social).map(([platform, handle]) => {
                  if (!handle) return null;
                  const meta = SOCIAL_MAP[platform.toLowerCase()];
                  const href = handle.startsWith('http') ? handle : `${meta?.base ?? ''}${handle}`;
                  return (
                    <a
                      key={platform}
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white hover:opacity-80 transition-opacity"
                      style={{ background: meta?.color ?? '#334155' }}
                    >
                      {meta?.label ?? platform}
                    </a>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Tags ── */}
          {tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {tags.map(t => (
                <span key={t} className="text-xs px-2.5 py-1 rounded-full bg-white/5 text-slate-400 border border-white/10">{t}</span>
              ))}
            </div>
          )}

          {/* ── Actions ── */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => onTriggerAudit(business)}
              className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm text-white transition-all hover:opacity-90"
              style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 4px 20px rgba(99,102,241,0.3)' }}
            >
              <ScanSearch size={15} />
              Trigger Audit
            </button>
            <a
              href={`/dashboard/leads`}
              className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm text-slate-300 hover:text-white transition-colors"
              style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
            >
              <Eye size={15} />
              Full Profile
            </a>
            <button
              onClick={() => enrichContacts()}
              disabled={enriching || enriched}
              className="col-span-2 flex items-center justify-center gap-2 py-2.5 rounded-xl font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-60"
              style={{ background: enriched ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.05)', border: `1px solid ${enriched ? 'rgba(16,185,129,0.3)' : 'rgba(255,255,255,0.1)'}`, color: enriched ? '#6ee7b7' : '#94a3b8' }}
            >
              {enriching ? (
                <><span className="w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" /> Fetching contacts…</>
              ) : enriched ? (
                <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg> Contacts updated — refresh to see</>
              ) : (
                <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg> Fetch Email &amp; Phone from Website</>
              )}
            </button>
            {onDelete && (
              <button
                onClick={() => {
                  onDelete(business);
                  onClose();
                }}
                className="col-span-2 flex items-center justify-center gap-2 py-2.5 rounded-xl font-semibold text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 border border-red-500/20 transition-all cursor-pointer"
              >
                <Trash2 size={13} />
                <span>Delete Lead from Database</span>
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

// ─── 1-Click Rapid Outreach Hub Modal ─────────────────────────────────────────

function RapidOutreachHubModal({
  leads,
  dealByBusinessId,
  onClose,
  onMarkContacted,
  onDeleteLead,
}: {
  leads: Business[];
  dealByBusinessId: Map<string, DealRaw>;
  onClose: () => void;
  onMarkContacted: (businessId: string, channel: string) => Promise<void>;
  onDeleteLead?: (businessId: string) => Promise<void>;
}) {
  const [index, setIndex] = useState(0);
  const [pitchVariant, setPitchVariant] = useState<'store' | 'whatsapp' | 'speed'>('store');
  const [customText, setCustomText] = useState('');
  const [copied, setCopied] = useState(false);
  const [loadingAction, setLoadingAction] = useState(false);

  // Filter to leads that are not already contacted
  const uncontactedLeads = useMemo(() => {
    return leads.filter((b) => {
      const deal = dealByBusinessId.get(b.id);
      return !deal || deal.stage === 'lead';
    });
  }, [leads, dealByBusinessId]);

  const activeLead = uncontactedLeads[index] || null;

  // Build custom pitch for activeLead
  const currentPitch = useMemo(() => {
    if (!activeLead) return '';
    const name = activeLead.name;
    const city = activeLead.city || 'your area';

    if (pitchVariant === 'store') {
      return `Assalam-o-Alaikum! 👋 Came across ${name} on Instagram in ${city}. Loved your collection! I noticed you don't have a direct website/catalog yet so customers must order manually through DMs. We help brands launch seamless mobile shopping websites that take orders directly via WhatsApp with zero hassle. Can I share a quick 2-minute demo store preview for ${name}?`;
    } else if (pitchVariant === 'whatsapp') {
      return `Hi ${name} team! Are you losing sales when customers ask for prices in Instagram DMs? We build fast online catalogs with 1-click WhatsApp checkout so customers can browse your collection and send complete cart orders directly to your WhatsApp. Would you like to see a free preview mockup for ${name}?`;
    } else {
      return `Hi! Loved ${name}'s page. A dedicated branded mobile website can double your customer trust and increase repeat sales. We build lightning-fast web stores for Instagram brands in ${city}. Can I send a free design concept for ${name}?`;
    }
  }, [activeLead, pitchVariant]);

  // Sync customText when currentPitch changes
  React.useEffect(() => {
    setCustomText(currentPitch);
  }, [currentPitch]);

  const total = uncontactedLeads.length;
  const progressPct = total > 0 ? Math.round(((index + 1) / total) * 100) : 100;

  const handleCopy = () => {
    if (!customText) return;
    navigator.clipboard.writeText(customText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleLaunchWhatsApp = async () => {
    if (!activeLead) return;
    setLoadingAction(true);
    const waUrl = toWhatsAppUrl(activeLead.phone, customText) || `https://wa.me/?text=${encodeURIComponent(customText)}`;
    window.open(waUrl, '_blank');
    try {
      await onMarkContacted(activeLead.id, 'whatsapp');
    } catch {}
    setLoadingAction(false);
    if (index >= uncontactedLeads.length - 1) {
      setIndex(0);
    }
  };

  const handleLaunchInstagram = async () => {
    if (!activeLead) return;
    setLoadingAction(true);
    navigator.clipboard.writeText(customText);
    setCopied(true);
    const igUrl = activeLead.instagramUrl
      ? (activeLead.instagramUrl.startsWith('http') ? activeLead.instagramUrl : `https://instagram.com/${activeLead.instagramUrl.replace('@', '')}`)
      : `https://instagram.com/`;
    window.open(igUrl, '_blank');
    try {
      await onMarkContacted(activeLead.id, 'instagram');
    } catch {}
    setLoadingAction(false);
    if (index >= uncontactedLeads.length - 1) {
      setIndex(0);
    }
  };

  const handleSkip = () => {
    if (index < total - 1) {
      setIndex(index + 1);
    } else {
      setIndex(0);
    }
  };

  const handlePrev = () => {
    if (index > 0) setIndex(index - 1);
  };

  const handleDeleteCurrent = async () => {
    if (!activeLead) return;
    if (!window.confirm(`Permanently delete "${activeLead.name}"?`)) return;
    setLoadingAction(true);
    try {
      if (onDeleteLead) {
        await onDeleteLead(activeLead.id);
      } else {
        await businessesApi.delete(activeLead.id);
      }
      if (index >= uncontactedLeads.length - 1) {
        setIndex(Math.max(0, uncontactedLeads.length - 2));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingAction(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 15 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 15 }}
          onClick={(e) => e.stopPropagation()}
          className="w-full max-w-3xl rounded-2xl overflow-hidden flex flex-col max-h-[90vh]"
          style={{
            background: 'rgba(14,14,32,0.98)',
            border: '1px solid rgba(99,102,241,0.3)',
            boxShadow: '0 25px 70px rgba(0,0,0,0.8), 0 0 40px rgba(99,102,241,0.15)',
          }}
        >
          {/* Header */}
          <div className="px-6 py-4 flex items-center justify-between border-b border-white/10" style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(168,85,247,0.1))' }}>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center text-white shadow-lg shadow-indigo-500/30">
                <Zap size={20} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-white">1-Click Rapid Outreach Hub</h2>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    Live CRM Sync
                  </span>
                </div>
                <p className="text-xs text-slate-400">Step through verified zero-website leads &amp; dispatch personalized pitches</p>
              </div>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors">
              <X size={18} />
            </button>
          </div>

          {/* Body */}
          {total === 0 || !activeLead ? (
            <div className="p-10 flex flex-col items-center justify-center text-center space-y-4">
              <div className="w-16 h-16 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-2xl">
                🎉
              </div>
              <h3 className="text-lg font-bold text-white">All Discovered Leads Contacted!</h3>
              <p className="text-sm text-slate-400 max-w-md">
                Every zero-website lead in this batch has been contacted and automatically moved to the <span className="text-indigo-300 font-semibold">&ldquo;Contacted&rdquo;</span> stage in your CRM pipeline.
              </p>
              <div className="flex items-center gap-3 pt-2">
                <a
                  href="/dashboard/crm"
                  className="px-5 py-2.5 rounded-xl text-sm font-semibold text-white transition-all shadow-lg shadow-indigo-500/30"
                  style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)' }}
                >
                  Open CRM Pipeline →
                </a>
                <button
                  onClick={onClose}
                  className="px-4 py-2.5 rounded-xl text-sm font-medium text-slate-300 hover:text-white border border-white/10"
                >
                  Close
                </button>
              </div>
            </div>
          ) : (
            <div className="p-6 overflow-y-auto space-y-5 flex-1">
              {/* Progress counter */}
              <div className="flex items-center justify-between text-xs text-slate-400">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-white">Lead {index + 1} of {total}</span>
                  <span>·</span>
                  <span className="text-indigo-400 font-medium">{total - index - 1} remaining in queue</span>
                </div>
                <span>{progressPct}% Completed</span>
              </div>
              <div className="w-full bg-white/5 rounded-full h-1.5 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-300"
                  style={{ width: `${progressPct}%` }}
                />
              </div>

              {/* Lead Card Summary */}
              <div
                className="p-4 rounded-xl border border-white/10 flex items-start justify-between gap-4"
                style={{ background: 'rgba(255,255,255,0.03)' }}
              >
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-lg font-bold text-white">{activeLead.name}</h3>
                    <Badge variant={industryColor(activeLead.industry) as any} size="sm">
                      {activeLead.industry || 'Social Seller'}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
                    <span className="flex items-center gap-1">
                      <MapPin size={12} className="text-indigo-400" />
                      {activeLead.city || 'Pakistan'}, {activeLead.country}
                    </span>
                    {activeLead.phone && (
                      <span className="flex items-center gap-1 font-mono text-emerald-400">
                        <Phone size={12} />
                        {activeLead.phone}
                      </span>
                    )}
                    {activeLead.instagramUrl && (
                      <span className="flex items-center gap-1 font-mono text-pink-400">
                        <Instagram size={12} />
                        {activeLead.instagramUrl.replace(/^https?:\/\/(www\.)?instagram\.com\//i, '@')}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex flex-col items-end gap-1 flex-shrink-0">
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                    <ShieldCheck size={12} />
                    Verified: 0 Website
                  </span>
                  <span className="text-[10px] text-slate-500">
                    Stage: <span className="text-amber-400">Lead</span> → <span className="text-indigo-300">Contacted</span>
                  </span>
                </div>
              </div>

              {/* Pitch Script Box */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1 bg-white/5 p-1 rounded-lg border border-white/5">
                    <button
                      onClick={() => setPitchVariant('store')}
                      className={`px-2.5 py-1 text-xs rounded-md font-medium transition-all ${pitchVariant === 'store' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}
                    >
                      🛍️ Web Store
                    </button>
                    <button
                      onClick={() => setPitchVariant('whatsapp')}
                      className={`px-2.5 py-1 text-xs rounded-md font-medium transition-all ${pitchVariant === 'whatsapp' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}
                    >
                      ⚡ WA Checkout
                    </button>
                    <button
                      onClick={() => setPitchVariant('speed')}
                      className={`px-2.5 py-1 text-xs rounded-md font-medium transition-all ${pitchVariant === 'speed' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}
                    >
                      📈 Conversion
                    </button>
                  </div>

                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 px-3 py-1 text-xs rounded-lg text-slate-300 hover:text-white bg-white/5 hover:bg-white/10 transition-all border border-white/10"
                  >
                    {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                    <span>{copied ? 'Copied Pitch' : 'Copy Pitch'}</span>
                  </button>
                </div>

                <textarea
                  value={customText}
                  onChange={(e) => setCustomText(e.target.value)}
                  rows={4}
                  className="w-full p-3.5 rounded-xl text-xs text-slate-200 font-sans leading-relaxed bg-black/40 border border-white/10 focus:outline-none focus:border-indigo-500/50 resize-none transition-colors"
                  placeholder="Tailored pitch text..."
                />
              </div>

              {/* Action Dispatch Buttons */}
              <div className="space-y-3 pt-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* WhatsApp Action */}
                  <button
                    onClick={handleLaunchWhatsApp}
                    disabled={loadingAction}
                    className="flex items-center justify-center gap-2 py-3 px-4 rounded-xl font-bold text-sm text-white transition-all shadow-lg active:scale-95 disabled:opacity-50 cursor-pointer"
                    style={{ background: '#25D366' }}
                  >
                    <Phone size={16} />
                    <span>Launch WhatsApp &amp; Advance</span>
                  </button>

                  {/* Instagram Action */}
                  <button
                    onClick={handleLaunchInstagram}
                    disabled={loadingAction}
                    className="flex items-center justify-center gap-2 py-3 px-4 rounded-xl font-bold text-sm text-white transition-all shadow-lg active:scale-95 disabled:opacity-50 cursor-pointer"
                    style={{
                      background: 'linear-gradient(135deg, #f09433, #e6683c 25%, #dc2743 50%, #cc2366 75%, #bc1888 100%)',
                    }}
                  >
                    <Instagram size={16} />
                    <span>Copy &amp; Open Instagram DM</span>
                  </button>
                </div>

                {/* Footer Navigation */}
                <div className="flex items-center justify-between pt-2">
                  <button
                    onClick={handlePrev}
                    disabled={index === 0}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs text-slate-400 hover:text-white disabled:opacity-30 transition-colors cursor-pointer"
                  >
                    <ChevronLeft size={14} />
                    <span>Previous Lead</span>
                  </button>

                  <button
                    onClick={handleDeleteCurrent}
                    disabled={loadingAction}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded-lg transition-all cursor-pointer"
                    title="Permanently remove this lead from database"
                  >
                    <Trash2 size={13} />
                    <span>Delete Lead</span>
                  </button>

                  <button
                    onClick={handleSkip}
                    className="flex items-center gap-1 px-4 py-1.5 text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/10 rounded-lg transition-all cursor-pointer"
                  >
                    <span>Skip to Next</span>
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// ─── New Job Modal ────────────────────────────────────────────────────────────

function NewJobModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [keywords, setKeywords] = useState('');
  const [city, setCity] = useState('');
  const [country, setCountry] = useState('');
  const [industry, setIndustry] = useState('');
  const [maxResults, setMaxResults] = useState(100);
  const [sources, setSources] = useState<string[]>(['instagram', 'facebook', 'reddit', 'ecommerce_brands', 'freelance']);
  const [websiteTarget, setWebsiteTarget] = useState<'all' | 'no_website' | 'has_website'>('no_website');
  const [saveWithEmail, setSaveWithEmail] = useState(false);
  const [saveWithWhatsApp, setSaveWithWhatsApp] = useState(false);

  const mutation = useMutation({
    mutationFn: (payload: DiscoveryJobCreatePayload) => discoveryApi.createJob(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery', 'jobs'] });
      onClose();
    },
  });

  // Auto-fill job name when keywords/city changes and name is still empty or auto-generated
  const autoName = React.useRef(true);
  React.useEffect(() => {
    if (!autoName.current) return;
    const parts = [keywords, city].filter(Boolean);
    if (parts.length) setName(parts.join(' in '));
  }, [keywords, city]);

  const toggleSource = (src: string) => {
    setSources((prev) =>
      prev.includes(src) ? prev.filter((s) => s !== src) : [...prev, src]
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: DiscoveryJobCreatePayload = {
      name,
      keywords,
      sources: sources.length > 0 ? sources : undefined,
      max_results: maxResults,
      filters: {
        save_with_website: websiteTarget === 'all' || websiteTarget === 'has_website',
        save_no_website: websiteTarget === 'all' || websiteTarget === 'no_website',
        require_email: saveWithEmail,
        require_whatsapp: saveWithWhatsApp,
      },
    };
    if (city.trim()) payload.city = city.trim();
    if (country.trim()) payload.country = country.trim();
    if (industry.trim()) payload.industry = industry.trim();
    mutation.mutate(payload);
  };

  const inputClass =
    'w-full px-3 py-2 rounded-lg border border-white/10 bg-white/5 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-colors';
  const labelClass = 'block text-xs font-medium text-slate-400 mb-1';

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.93, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.93, y: 20 }}
          transition={{ duration: 0.22 }}
          className="w-full max-w-lg rounded-2xl overflow-hidden"
          style={{
            background: 'rgba(14,14,32,0.98)',
            backdropFilter: 'blur(24px)',
            border: '1px solid rgba(255,255,255,0.1)',
            boxShadow: '0 40px 80px rgba(0,0,0,0.6)',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-6 py-4 border-b"
            style={{ borderColor: 'rgba(255,255,255,0.08)' }}
          >
            <div>
              <h2 className="text-lg font-bold text-white">New Discovery Job</h2>
              <p className="text-xs text-slate-400 mt-0.5">Configure and launch a new business discovery</p>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          {/* Body */}
          <form onSubmit={handleSubmit} className="p-6 space-y-4 overflow-y-auto" style={{ maxHeight: 'calc(90vh - 140px)' }}>
            {/* Job Name */}
            <div>
              <label className={labelClass}>Job Name <span className="text-red-400">*</span></label>
              <input
                type="text"
                placeholder="Auto-filled from keywords + city"
                value={name}
                onChange={(e) => { autoName.current = false; setName(e.target.value); }}
                required
                className={inputClass}
              />
            </div>

            {/* Keywords — combobox with presets */}
            <div>
              <label className={labelClass}>
                Business Type / Keywords <span className="text-red-400">*</span>
              </label>
              <ComboBox
                value={keywords}
                onChange={setKeywords}
                placeholder="e.g. Restaurants, Plumbers, Salons…"
                groups={KEYWORD_PRESETS}
                icon={<Search size={14} />}
                allowCustom
              />
              <p className="text-xs text-slate-500 mt-1">Pick from the list or type your own</p>
            </div>

            {/* City + Country — both comboboxes */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelClass}>City <span className="text-slate-600">(optional)</span></label>
                <ComboBox
                  value={city}
                  onChange={setCity}
                  placeholder="e.g. New York"
                  groups={CITY_PRESETS}
                  icon={<MapPin size={14} />}
                  allowCustom
                />
              </div>
              <div>
                <label className={labelClass}>Country <span className="text-slate-600">(optional)</span></label>
                <ComboBox
                  value={country}
                  onChange={setCountry}
                  placeholder="e.g. United States"
                  groups={COUNTRY_PRESETS}
                  icon={<Globe2 size={14} />}
                  allowCustom
                />
              </div>
            </div>

            {/* Industry — combobox */}
            <div>
              <label className={labelClass}>Industry <span className="text-slate-600">(optional)</span></label>
              <ComboBox
                value={industry}
                onChange={setIndustry}
                placeholder="e.g. Restaurant, Healthcare, Retail…"
                groups={INDUSTRY_PRESETS}
                icon={<Building2 size={14} />}
                allowCustom
              />
            </div>

            {/* Max Results — styled select */}
            <div>
              <label className={labelClass}>Max Results</label>
              <div className="relative">
                <select
                  value={maxResults}
                  onChange={(e) => setMaxResults(Number(e.target.value))}
                  className="appearance-none w-full px-3 py-2 rounded-lg border border-white/10 bg-white/5 text-sm text-slate-300 focus:outline-none focus:border-indigo-500/50 transition-colors cursor-pointer pr-8"
                >
                  {MAX_RESULTS_OPTIONS.map(o => (
                    <option key={o.value} value={o.value} className="bg-slate-900">{o.label}</option>
                  ))}
                </select>
                <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              </div>
            </div>

            {/* Sources */}
            <div>
              <label className={labelClass}>Data Sources <span className="text-slate-600 font-normal">(select one or both)</span></label>
              <div className="space-y-2">
                {[
                  { id: 'freelance', label: 'Freelance Platforms (Upwork, Freelancer, Fiverr)', note: '💼 Active paying clients & hiring projects with budgets on Upwork, Freelancer.com, and Fiverr.', badge: 'text-emerald-400', icon: '💼' },
                  { id: 'instagram', label: 'Instagram (Bio WhatsApp & DM Sellers)', note: '📸 Finds boutiques & shops with WhatsApp and NO website — highest conversion rate.', badge: 'text-pink-400', icon: '📸' },
                  { id: 'facebook', label: 'Facebook (Pages & Local Shops)', note: '👥 Verified Facebook business pages & shops with active mobile & WhatsApp contacts.', badge: 'text-blue-400', icon: '👥' },
                  { id: 'reddit', label: 'Reddit (Hiring & Client Leads)', note: '💬 Direct clients & founders actively seeking web developers in r/forhire & r/freelance.', badge: 'text-orange-400', icon: '💬' },
                  { id: 'ecommerce_brands', label: 'Daraz & E-Commerce Brands', note: '🛍️ Verified brand merchants with mobile WhatsApp (+92300-349) & store tech stacks.', badge: 'text-emerald-400', icon: '🛍️' },
                  { id: 'google_places', label: 'Google Places API (Recommended)', note: '✓ Real businesses worldwide with phone, address, website. Best source.', badge: 'text-green-400', icon: '✅' },
                  { id: 'google_maps', label: 'Google Maps Scraper', note: 'No API key needed — scrapes Maps directly. Slower but worldwide.', badge: 'text-sky-400', icon: '🗺️' },
                  { id: 'duckduckgo', label: 'DuckDuckGo Web Search', note: 'Finds business websites — good for emails & social links', badge: 'text-sky-400', icon: '🌐' },
                  { id: 'overpass', label: 'OSM Overpass API', note: 'Offline businesses without websites — requires City field', badge: 'text-amber-400', icon: '📍' },
                  { id: 'nominatim', label: 'OpenStreetMap (OSM)', note: 'Same as Overpass but slower — requires City field', badge: 'text-slate-400', icon: '🔵' },
                  { id: 'yelp', label: 'Yelp Fusion API', note: 'US/Canada only — requires YELP_API_KEY', badge: 'text-rose-400', icon: '⭐' },
                ].map(({ id, label, note, badge, icon }) => (
                  <label
                    key={id}
                    className="flex items-start gap-3 cursor-pointer select-none px-4 py-3 rounded-xl border transition-all"
                    style={{
                      borderColor: sources.includes(id) ? 'rgba(99,102,241,0.5)' : 'rgba(255,255,255,0.08)',
                      background: sources.includes(id) ? 'rgba(99,102,241,0.08)' : 'rgba(255,255,255,0.02)',
                    }}
                  >
                    <input type="checkbox" checked={sources.includes(id)} onChange={() => toggleSource(id)} className="accent-indigo-500 mt-0.5" />
                    <div>
                      <span className="text-sm text-white font-medium">{icon} {label}</span>
                      <span className={`block text-xs mt-0.5 ${badge}`}>{note}</span>
                    </div>
                  </label>
                ))}
              </div>
              <p className="text-xs text-slate-500 mt-2">
                Tip: Use <strong className="text-green-400">Google Places API</strong> for best results worldwide — real phone numbers, addresses, websites. Add <strong className="text-sky-400">DuckDuckGo</strong> to boost email coverage.
              </p>
              {(sources.includes('nominatim') || sources.includes('overpass')) && !city.trim() && (
                <p className="text-xs text-amber-400 mt-1">⚠️ OSM sources require a City — enter one above or they will return 0 results.</p>
              )}
            </div>

            {/* Website Target Filter */}
            <div>
              <label className={labelClass}>Website Target <span className="text-indigo-400 font-semibold">(Filter Leads)</span></label>
              <div className="grid grid-cols-3 gap-2 mb-3">
                {[
                  { id: 'no_website', label: 'No Website Only', note: 'DM/WhatsApp Sellers (Best for Selling Sites)', icon: <AlertCircle size={14} className="text-amber-400" /> },
                  { id: 'has_website', label: 'Has Website Only', note: 'Existing Sites (Best for SEO / Audits)', icon: <Globe size={14} className="text-emerald-400" /> },
                  { id: 'all', label: 'All Businesses', note: 'Save both with & without websites', icon: <ScanSearch size={14} className="text-sky-400" /> },
                ].map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setWebsiteTarget(opt.id as any)}
                    className={`p-3 rounded-xl border text-left transition-all flex flex-col justify-between ${
                      websiteTarget === opt.id
                        ? 'border-indigo-500 bg-indigo-500/15 shadow-sm shadow-indigo-500/20'
                        : 'border-white/10 bg-white/5 hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-1.5">
                      {opt.icon}
                      <span className={`text-xs font-semibold ${websiteTarget === opt.id ? 'text-white' : 'text-slate-300'}`}>
                        {opt.label}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 leading-tight">
                      {opt.note}
                    </span>
                  </button>
                ))}
              </div>

              {/* Contact Requirements */}
              <label className={labelClass}>Required Contact Channels <span className="text-slate-500 font-normal">(optional)</span></label>
              <div className="rounded-xl border border-white/10 overflow-hidden" style={{ background: 'rgba(255,255,255,0.02)' }}>
                {[
                  { label: 'Email Required', note: 'Only save if business email is found', color: 'text-blue-400', icon: <Mail size={13} />, checked: saveWithEmail, set: setSaveWithEmail },
                  { label: 'WhatsApp Required', note: 'Only save if active WhatsApp number is found', color: 'text-green-400', icon: <Phone size={13} />, checked: saveWithWhatsApp, set: setSaveWithWhatsApp },
                ].map(({ label, note, color, icon, checked, set }, i) => (
                  <label
                    key={label}
                    className="flex items-center gap-3 px-4 py-2.5 cursor-pointer select-none transition-colors hover:bg-white/4"
                    style={{ borderBottom: i === 0 ? '1px solid rgba(255,255,255,0.06)' : 'none' }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={e => set(e.target.checked)}
                      className="accent-indigo-500 w-4 h-4 flex-shrink-0"
                    />
                    <span className={`flex-shrink-0 ${color}`}>{icon}</span>
                    <div className="min-w-0">
                      <span className="text-xs text-white font-medium">{label}</span>
                      <span className={`block text-[10px] ${color}`}>{note}</span>
                    </div>
                    {checked && (
                      <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ background: 'rgba(99,102,241,0.2)', color: '#a5b4fc' }}>REQUIRED</span>
                    )}
                  </label>
                ))}
              </div>
            </div>

            {/* Error */}
            {mutation.isError && (
              <p className="text-xs text-red-400">
                {(mutation.error as Error)?.message ?? 'Failed to create job. Please try again.'}
              </p>
            )}
          </form>

          {/* Footer */}
          <div
            className="flex items-center gap-3 px-6 py-4 border-t"
            style={{ borderColor: 'rgba(255,255,255,0.08)' }}
          >
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 rounded-xl text-sm text-slate-400 hover:text-white hover:bg-white/8 transition-colors border border-white/10"
            >
              Cancel
            </button>
            <button
              type="submit"
              form="new-job-form"
              onClick={handleSubmit}
              disabled={mutation.isPending || !name.trim() || !keywords.trim()}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl font-semibold text-sm text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 4px 20px rgba(99,102,241,0.4)' }}
            >
              {mutation.isPending ? (
                <>
                  <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
                    <RefreshCw size={15} />
                  </motion.div>
                  Creating…
                </>
              ) : (
                <>
                  <Play size={15} />
                  Start Discovery
                </>
              )}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DiscoveryCenterPage() {
  const queryClient = useQueryClient();
  const [showNewJob, setShowNewJob] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState('');
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [industry, setIndustry] = useState('All Industries');
  const [country, setCountry] = useState('All Countries');
  const [filterWebsite, setFilterWebsite] = useState<'all' | 'yes' | 'no'>('all');
  const [filterEmail, setFilterEmail] = useState(false);
  const [filterWhatsApp, setFilterWhatsApp] = useState(false);
  const [search, setSearch] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [selectedBusiness, setSelectedBusiness] = useState<Business | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);

  // Round / Batch filtering & Delete states
  const [selectedJobId, setSelectedJobId] = useState<string>('all');
  const [selectedBusinessIds, setSelectedBusinessIds] = useState<Set<string>>(new Set());
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearingLeads, setClearingLeads] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // Auto-Pilot & Outreach Hub States
  const [autopilotNiche, setAutopilotNiche] = useState('Clothing & Boutiques');
  const [autopilotCity, setAutopilotCity] = useState('Lahore');
  const [autopilotCountry, setAutopilotCountry] = useState('Pakistan');
  const [autopilotCount, setAutopilotCount] = useState(15);
  const [autopilotRunning, setAutopilotRunning] = useState(false);
  const [autopilotMsg, setAutopilotMsg] = useState<string | null>(null);
  const [showOutreachHub, setShowOutreachHub] = useState(false);
  const [sweepRunning, setSweepRunning] = useState(false);

  const { data: autoStatus, refetch: refetchAutoStatus } = useQuery({
    queryKey: ['discovery', 'autopilot-status'],
    queryFn: () => discoveryApi.getAutopilotStatus(),
    refetchInterval: 8_000,
  });

  const { data: jobsData } = useQuery({
    queryKey: ['discovery', 'jobs'],
    queryFn: () => discoveryApi.listJobs({ page: 1, page_size: 20 }),
    refetchInterval: (query) => {
      const jobs: DiscoveryJobRaw[] = query.state.data?.items ?? [];
      const hasActive = jobs.some((j) => j.status === 'pending' || j.status === 'running');
      return hasActive ? 3_000 : 15_000;
    },
  });

  const rerunMutation = useMutation({
    mutationFn: (id: string) => discoveryApi.rerunJob(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery', 'jobs'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => discoveryApi.deleteJob(id),
    onSuccess: () => {
      setDeletingJobId(null);
      queryClient.invalidateQueries({ queryKey: ['discovery', 'jobs'] });
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
    },
  });

  const { data: businessData, isLoading: loadingBusinesses } = useQuery({
    queryKey: ['businesses', 'discovery', industry, country, filterWebsite, selectedJobId],
    queryFn: () => businessesApi.list({
      page: 1,
      page_size: 200,
      industry: industry !== 'All Industries' ? industry : undefined,
      country: country !== 'All Countries' ? country : undefined,
      has_website: filterWebsite === 'yes' ? true : filterWebsite === 'no' ? false : undefined,
      job_id: selectedJobId !== 'all' ? selectedJobId : undefined,
    }),
    refetchInterval: 15_000,
  });

  // Query CRM Deals to keep tabs on contacted leads
  const { data: dealsData } = useQuery({
    queryKey: ['crm', 'deals'],
    queryFn: () => crmApi.listDeals(),
    refetchInterval: 10_000,
  });

  const dealByBusinessId = useMemo(() => {
    const map = new Map<string, DealRaw>();
    (dealsData || []).forEach((d) => map.set(d.business_id, d));
    return map;
  }, [dealsData]);

  const allJobs = useMemo<DiscoveryJob[]>(() => (jobsData?.items ?? []).map(rawToJob), [jobsData]);
  const allBusinesses = useMemo<Business[]>(() => (businessData?.items ?? []).map(rawToBusiness), [businessData]);

  // Zero-Website Uncontacted Leads queue
  const uncontactedZeroWebLeads = useMemo(() => {
    return allBusinesses.filter((b) => {
      if (b.hasWebsite || Boolean(b.website)) return false;
      const deal = dealByBusinessId.get(b.id);
      return !deal || deal.stage === 'lead';
    });
  }, [allBusinesses, dealByBusinessId]);

  // Filtered businesses
  const filteredBusinesses = useMemo(() => {
    return allBusinesses.filter((b) => {
      if (search && !b.name.toLowerCase().includes(search.toLowerCase()) && !b.industry.toLowerCase().includes(search.toLowerCase())) return false;
      if (filterEmail && !b.email) return false;
      if (filterWhatsApp && !toWhatsAppUrl(b.phone, '')) return false;
      if (filterWebsite === 'yes' && (!b.hasWebsite || !b.website)) return false;
      if (filterWebsite === 'no' && (b.hasWebsite || Boolean(b.website))) return false;
      return true;
    });
  }, [allBusinesses, search, filterEmail, filterWhatsApp, filterWebsite]);

  const stats = useMemo(() => {
    const total = businessData?.total ?? 0;
    const thisWeek = allBusinesses.filter(
      (b) => new Date(b.discoveredAt) >= new Date(Date.now() - 7 * 86400000)
    ).length;
    const withWeb = allBusinesses.filter((b) => b.hasWebsite && Boolean(b.website)).length;
    const withoutWeb = allBusinesses.filter((b) => !b.hasWebsite || !b.website).length;
    return { total, thisWeek, withWeb, withoutWeb };
  }, [allBusinesses, businessData]);

  const handleTriggerAudit = async (b: Business) => {
    setSelectedBusiness(null);
    try {
      await businessesApi.triggerAudit(b.id);
    } catch {
      // audit queued or already running — navigate anyway
    }
    window.location.href = `/dashboard/audit`;
  };

  const handleLaunchAutopilot = async () => {
    setAutopilotRunning(true);
    setAutopilotMsg(null);
    try {
      const res = await discoveryApi.startAutopilot({
        city: autopilotCity,
        country: autopilotCountry,
        target_count: autopilotCount,
        industry: autopilotNiche,
      });
      setAutopilotMsg(`✓ Auto-Pilot engine started for ${res.city} (${res.target_count} leads target). Scanning Instagram...`);
      queryClient.invalidateQueries({ queryKey: ['discovery', 'jobs'] });
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
      queryClient.invalidateQueries({ queryKey: ['crm', 'deals'] });
    } catch (err: unknown) {
      setAutopilotMsg(`Error: ${(err as Error).message || 'Failed to start auto-pilot'}`);
    } finally {
      setTimeout(() => setAutopilotRunning(false), 2000);
    }
  };

  const handleLaunchSweep = async (regionPreset: 'gulf' | 'pakistan' | 'uk_us' = 'gulf') => {
    setSweepRunning(true);
    setAutopilotMsg(null);
    let sweepCities = ['Dubai', 'Abu Dhabi', 'Riyadh', 'Doha'];
    let sweepTitle = '🇦🇪 🇸🇦 Gulf Sweep';
    if (regionPreset === 'pakistan') {
      sweepCities = ['Lahore', 'Karachi', 'Islamabad', 'Rawalpindi'];
      sweepTitle = '🇵🇰 Pakistan Sweep';
    } else if (regionPreset === 'uk_us') {
      sweepCities = ['London', 'Manchester', 'New York', 'Miami'];
      sweepTitle = '🇬🇧 🇺🇸 UK & US Sweep';
    }
    try {
      const res = await discoveryApi.sweepAutopilot({
        cities: sweepCities,
        niches: [autopilotNiche, 'Clothing & Boutiques'],
        batch_per_city: 10,
      });
      setAutopilotMsg(`✓ ${sweepTitle} launched across ${res.cities.join(', ')} (${res.jobs_count} concurrent background jobs scanning Instagram!)`);
      queryClient.invalidateQueries({ queryKey: ['discovery', 'jobs'] });
      queryClient.invalidateQueries({ queryKey: ['discovery', 'autopilot-status'] });
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
    } catch (err: unknown) {
      setAutopilotMsg(`Error: ${(err as Error).message || 'Sweep failed to start'}`);
    } finally {
      setTimeout(() => setSweepRunning(false), 2500);
    }
  };

  const handleToggleCruise = async () => {
    try {
      const nextState = !autoStatus?.cruise_enabled;
      const res = await discoveryApi.toggleCruise({
        enabled: nextState,
        interval_minutes: 30,
        cities: ['Dubai', 'Abu Dhabi', 'Riyadh', 'Doha', 'Lahore', 'Karachi', 'London'],
        niches: [autopilotNiche, 'Clothing & Boutiques', 'Bakeries & Custom Cakes'],
      });
      setAutopilotMsg(res.message);
      refetchAutoStatus();
      queryClient.invalidateQueries({ queryKey: ['discovery', 'jobs'] });
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
    } catch (err: unknown) {
      setAutopilotMsg(`Error: ${(err as Error).message || 'Cruise toggle failed'}`);
    }
  };

  const handleMarkContacted = async (businessId: string, channel: string) => {
    try {
      await discoveryApi.markContacted(businessId, channel);
      queryClient.invalidateQueries({ queryKey: ['crm', 'deals'] });
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
    } catch (err) {
      console.error('Failed to mark contacted', err);
    }
  };

  const handleQuickWhatsApp = async (b: Business, e: React.MouseEvent) => {
    e.stopPropagation();
    const pitch = `Assalam-o-Alaikum! 👋 Came across ${b.name} on Instagram in ${b.city || 'your city'}. Loved your collection! We help social brands launch high-speed mobile web stores with 1-click WhatsApp checkout so customers don't abandon orders in DMs. Can I share a quick 2-minute demo store preview for ${b.name}?`;
    const waUrl = toWhatsAppUrl(b.phone, pitch) || `https://wa.me/?text=${encodeURIComponent(pitch)}`;
    window.open(waUrl, '_blank');
    await handleMarkContacted(b.id, 'whatsapp');
  };

  const handleQuickInstagram = async (b: Business, e: React.MouseEvent) => {
    e.stopPropagation();
    const pitch = `Assalam-o-Alaikum! 👋 Came across ${b.name} on Instagram in ${b.city || 'your city'}. Loved your collection! We help social brands launch high-speed mobile web stores with 1-click WhatsApp checkout so customers don't abandon orders in DMs. Can I share a quick 2-minute demo store preview for ${b.name}?`;
    navigator.clipboard.writeText(pitch);
    const igUrl = b.instagramUrl
      ? (b.instagramUrl.startsWith('http') ? b.instagramUrl : `https://instagram.com/${b.instagramUrl.replace('@', '')}`)
      : `https://instagram.com/`;
    window.open(igUrl, '_blank');
    await handleMarkContacted(b.id, 'instagram');
  };

  const toggleSelectBusiness = (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setSelectedBusinessIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedBusinessIds(new Set(filteredBusinesses.map((b) => b.id)));
    } else {
      setSelectedBusinessIds(new Set());
    }
  };

  const handleDeleteSingleLead = async (b: Business, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!window.confirm(`Permanently delete "${b.name}"? This removes it and its CRM deals.`)) {
      return;
    }
    try {
      await businessesApi.delete(b.id);
      setSelectedBusinessIds((prev) => {
        const next = new Set(prev);
        next.delete(b.id);
        return next;
      });
      if (selectedBusiness?.id === b.id) {
        setSelectedBusiness(null);
      }
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
      queryClient.invalidateQueries({ queryKey: ['crm', 'deals'] });
    } catch (err: unknown) {
      alert(`Failed to delete lead: ${(err as Error).message || 'Error'}`);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedBusinessIds.size === 0) return;
    const count = selectedBusinessIds.size;
    if (!window.confirm(`Permanently delete all ${count} selected leads and associated CRM deals?`)) {
      return;
    }
    setBulkDeleting(true);
    try {
      const ids = Array.from(selectedBusinessIds);
      await businessesApi.bulkDelete(ids);
      setSelectedBusinessIds(new Set());
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
      queryClient.invalidateQueries({ queryKey: ['crm', 'deals'] });
    } catch (err: unknown) {
      alert(`Failed to delete leads: ${(err as Error).message || 'Error'}`);
    } finally {
      setBulkDeleting(false);
    }
  };

  const handleConfirmClear = async () => {
    setClearingLeads(true);
    try {
      await businessesApi.clearAll({
        job_id: selectedJobId !== 'all' ? selectedJobId : undefined,
        has_website: filterWebsite === 'yes' ? true : filterWebsite === 'no' ? false : undefined,
      });
      setSelectedBusinessIds(new Set());
      setShowClearConfirm(false);
      queryClient.invalidateQueries({ queryKey: ['businesses'] });
      queryClient.invalidateQueries({ queryKey: ['crm', 'deals'] });
      queryClient.invalidateQueries({ queryKey: ['discovery', 'jobs'] });
    } catch (err: unknown) {
      alert(`Failed to clear leads: ${(err as Error).message || 'Error'}`);
    } finally {
      setClearingLeads(false);
    }
  };

  return (
    <div className="p-6 space-y-6 min-h-full">
      {/* ── Header ── */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Discovery Center</h1>
          <p className="text-sm text-slate-400 mt-1">Automatically find high-converting zero-website businesses and launch client outreach</p>
        </div>
        <div className="flex items-center gap-3">
          {uncontactedZeroWebLeads.length > 0 && (
            <button
              onClick={() => setShowOutreachHub(true)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold text-sm text-white transition-all shadow-lg active:scale-95"
              style={{
                background: 'linear-gradient(135deg, #10b981 0%, #6366f1 100%)',
                boxShadow: '0 4px 20px rgba(16, 185, 129, 0.4)',
              }}
            >
              <Zap size={15} />
              <span>1-Click Outreach Hub ({uncontactedZeroWebLeads.length})</span>
            </button>
          )}
          <button
            onClick={() => setShowImport(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-sm text-slate-300 border border-white/10 hover:border-white/20 hover:text-white transition-all"
            style={{ background: 'rgba(255,255,255,0.05)' }}
          >
            <Upload size={16} />
            Import List
          </button>
          <button
            onClick={() => setShowNewJob(true)}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm text-white transition-all hover:opacity-90 active:scale-95"
            style={{
              background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
              boxShadow: '0 4px 20px rgba(99,102,241,0.4)',
            }}
          >
            <Plus size={16} />
            New Discovery Job
          </button>
        </div>
      </div>

      {/* ── Separate Freelance Hub Callout Banner ── */}
      <div className="flex items-center justify-between gap-4 p-4 rounded-2xl bg-gradient-to-r from-emerald-950/40 via-teal-950/30 to-indigo-950/40 border border-emerald-500/25 shadow-lg">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex-shrink-0">
            <Briefcase size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-white">Dedicated Freelance Client Hub</h3>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">DEDICATED PAGE</span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Looking to mine live hiring projects from <strong className="text-emerald-400">Upwork</strong>, <strong className="text-sky-400">Freelancer.com</strong>, and <strong className="text-teal-400">Fiverr</strong> with AI proposal generation? We built a dedicated page for it.
            </p>
          </div>
        </div>
        <Link
          href="/dashboard/freelance"
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 transition-all flex-shrink-0 shadow-md cursor-pointer"
        >
          <span>Open Freelance Hub</span>
          <ArrowRight size={13} />
        </Link>
      </div>

      {/* ── Auto-Pilot Engine Banner ── */}
      <div
        className="rounded-2xl p-5 border relative overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, rgba(20, 16, 45, 0.85) 0%, rgba(13, 13, 30, 0.95) 100%)',
          borderColor: 'rgba(99, 102, 241, 0.35)',
          boxShadow: '0 12px 40px rgba(0, 0, 0, 0.4), 0 0 24px rgba(99, 102, 241, 0.1)',
        }}
      >
        <div className="flex items-center justify-between gap-4 flex-wrap mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-indigo-500/30">
              <Bot size={22} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white">⚡ Auto-Pilot Lead Engine</h2>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  Fully Automated
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Discovers active Instagram social sellers with strict multi-layer verification (HTTP probe + bio link scan) to ensure 100% zero-website leads, and auto-syncs deals into your CRM.
              </p>
            </div>
          </div>

          {/* Verification safeguards badges */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20">
              <ShieldCheck size={13} />
              Live HTTP Domain Probe
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-sky-400 bg-sky-500/10 px-2.5 py-1 rounded-lg border border-sky-500/20">
              <Phone size={12} />
              Direct Mobile WhatsApp Only
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-purple-400 bg-purple-500/10 px-2.5 py-1 rounded-lg border border-purple-500/20">
              <Sparkles size={12} />
              Auto CRM Deal Sync
            </span>
            {autoStatus?.cruise_enabled && (
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-emerald-300 bg-emerald-500/20 px-2.5 py-1 rounded-lg border border-emerald-400/30 animate-pulse">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                24/7 Cruise Mode Running
              </span>
            )}
          </div>
        </div>

        {/* Quick Niche Presets */}
        <div className="flex items-center gap-2 flex-wrap mb-4">
          <span className="text-xs text-slate-400 font-medium mr-1">Target Niche:</span>
          {[
            { label: "👗 Boutiques & Clothing", value: "Clothing & Boutiques" },
            { label: "💍 Jewellery & Silver", value: "Jewellery & Accessories" },
            { label: "🧁 Bakeries & Cakes", value: "Bakeries & Custom Cakes" },
            { label: "✂️ Salons & Beauty", value: "Beauty & Salons" },
            { label: "👟 Footwear & Bags", value: "Footwear & Leather" },
            { label: "🍔 Gourmet Cloud Kitchens", value: "Food & Cloud Kitchens" },
          ].map((item) => (
            <button
              key={item.value}
              onClick={() => setAutopilotNiche(item.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                autopilotNiche === item.value
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/30 font-semibold'
                  : 'bg-white/5 text-slate-300 hover:text-white hover:bg-white/10 border border-white/5'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Auto-Pilot Trigger Controls */}
        <div className="flex items-center gap-3 flex-wrap pt-1 border-t border-white/5">
          {/* City */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">Quick Market:</span>
            <div className="flex items-center gap-1 bg-white/5 rounded-lg p-1 border border-white/10 flex-wrap">
              {[
                { label: 'Dubai', city: 'Dubai', country: 'United Arab Emirates' },
                { label: 'Abu Dhabi', city: 'Abu Dhabi', country: 'United Arab Emirates' },
                { label: 'Riyadh', city: 'Riyadh', country: 'Saudi Arabia' },
                { label: 'Doha', city: 'Doha', country: 'Qatar' },
                { label: 'Kuwait', city: 'Kuwait City', country: 'Kuwait' },
                { label: 'Lahore', city: 'Lahore', country: 'Pakistan' },
                { label: 'Karachi', city: 'Karachi', country: 'Pakistan' },
                { label: 'London', city: 'London', country: 'United Kingdom' },
                { label: 'New York', city: 'New York', country: 'United States' },
              ].map((item) => (
                <button
                  key={item.label}
                  onClick={() => {
                    setAutopilotCity(item.city);
                    setAutopilotCountry(item.country);
                  }}
                  className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors cursor-pointer ${
                    autopilotCity === item.city ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {/* Custom City input & Country Tag */}
          <div className="flex items-center gap-2 min-w-[200px] max-w-sm">
            <input
              type="text"
              placeholder="Or type any city..."
              value={autopilotCity}
              onChange={(e) => setAutopilotCity(e.target.value)}
              className="flex-1 px-3 py-1.5 rounded-lg border border-white/10 bg-white/5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50"
            />
            {autopilotCountry && (
              <span className="text-[11px] px-2 py-1 rounded bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 font-medium whitespace-nowrap">
                📍 {autopilotCountry}
              </span>
            )}
          </div>

          {/* Batch Count */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">Batch:</span>
            <div className="flex items-center gap-1 bg-white/5 rounded-lg p-1 border border-white/10">
              {[10, 20, 30].map((cnt) => (
                <button
                  key={cnt}
                  onClick={() => setAutopilotCount(cnt)}
                  className={`px-2 py-1 text-xs rounded-md font-medium transition-colors cursor-pointer ${
                    autopilotCount === cnt ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {cnt} Leads
                </button>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="ml-auto flex items-center gap-2 flex-wrap">
            {/* Cruise Mode Toggle */}
            <button
              onClick={handleToggleCruise}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl font-bold text-xs transition-all shadow-md active:scale-95 border cursor-pointer ${
                autoStatus?.cruise_enabled
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-emerald-500/20'
                  : 'bg-white/5 text-slate-300 hover:text-white border-white/10 hover:bg-white/10'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${autoStatus?.cruise_enabled ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
              <span>{autoStatus?.cruise_enabled ? '🤖 Cruise: Active' : '🤖 Cruise: Off'}</span>
            </button>

            {/* Gulf Sweep Button */}
            <button
              onClick={() => handleLaunchSweep('gulf')}
              disabled={sweepRunning}
              title="Auto-scan Dubai, Abu Dhabi, Riyadh, Doha"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl font-bold text-xs text-white transition-all shadow-md active:scale-95 disabled:opacity-50 cursor-pointer border border-emerald-400/30"
              style={{
                background: 'linear-gradient(135deg, #059669 0%, #0d9488 100%)',
                boxShadow: '0 4px 14px rgba(5,150,105,0.25)',
              }}
            >
              <Sparkles size={13} className={sweepRunning ? 'animate-spin text-amber-200' : 'text-amber-200'} />
              <span>🇦🇪 🇸🇦 Gulf Sweep</span>
            </button>

            {/* Pakistan Sweep Button */}
            <button
              onClick={() => handleLaunchSweep('pakistan')}
              disabled={sweepRunning}
              title="Auto-scan Lahore, Karachi, Islamabad, Rawalpindi"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl font-bold text-xs text-white transition-all shadow-md active:scale-95 disabled:opacity-50 cursor-pointer border border-teal-500/30"
              style={{
                background: 'linear-gradient(135deg, #0f766e 0%, #047857 100%)',
                boxShadow: '0 4px 14px rgba(15,118,110,0.25)',
              }}
            >
              <Sparkles size={13} className={sweepRunning ? 'animate-spin text-teal-200' : 'text-teal-200'} />
              <span>🇵🇰 PK Sweep</span>
            </button>

            {/* UK & US Sweep Button */}
            <button
              onClick={() => handleLaunchSweep('uk_us')}
              disabled={sweepRunning}
              title="Auto-scan London, Manchester, New York, Miami"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl font-bold text-xs text-white transition-all shadow-md active:scale-95 disabled:opacity-50 cursor-pointer border border-blue-500/30"
              style={{
                background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
                boxShadow: '0 4px 14px rgba(37,99,235,0.25)',
              }}
            >
              <Sparkles size={13} className={sweepRunning ? 'animate-spin text-sky-200' : 'text-sky-200'} />
              <span>🇬🇧 🇺🇸 UK/US Sweep</span>
            </button>

            {/* Single Target Launch Button */}
            <button
              onClick={handleLaunchAutopilot}
              disabled={autopilotRunning}
              className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-xs text-white transition-all shadow-lg active:scale-95 disabled:opacity-50 cursor-pointer"
              style={{
                background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
                boxShadow: '0 4px 20px rgba(99,102,241,0.4)',
              }}
            >
              <Zap size={14} className={autopilotRunning ? 'animate-bounce text-amber-300' : 'text-amber-300'} />
              <span>{autopilotRunning ? 'Scanning...' : '⚡ Launch City'}</span>
            </button>
          </div>
        </div>

        {autopilotMsg && (
          <div className={`mt-3 text-xs px-3 py-2 rounded-lg ${autopilotMsg.startsWith('Error') ? 'text-red-300 bg-red-500/10' : 'text-emerald-300 bg-emerald-500/10'}`}>
            {autopilotMsg}
          </div>
        )}
      </div>

      {/* ── 1-Click Rapid Outreach Hub Trigger Bar ── */}
      {uncontactedZeroWebLeads.length > 0 && (
        <div
          className="rounded-xl px-5 py-3.5 flex items-center justify-between gap-4 flex-wrap border"
          style={{
            background: 'linear-gradient(90deg, rgba(16, 185, 129, 0.1) 0%, rgba(99, 102, 241, 0.12) 100%)',
            borderColor: 'rgba(16, 185, 129, 0.3)',
            boxShadow: '0 4px 20px rgba(16, 185, 129, 0.1)',
          }}
        >
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold">
              🚀
            </div>
            <div>
              <p className="font-semibold text-emerald-300 text-sm">
                {uncontactedZeroWebLeads.length} High-Converting Zero-Website Leads Ready for Outreach
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                Speed-pitch via WhatsApp or Instagram DM and instantly advance deals in your CRM pipeline.
              </p>
            </div>
          </div>

          <button
            onClick={() => setShowOutreachHub(true)}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-xs text-white transition-all shadow-md active:scale-95 hover:opacity-95 cursor-pointer"
            style={{
              background: 'linear-gradient(135deg, #10b981 0%, #6366f1 100%)',
              boxShadow: '0 4px 16px rgba(16,185,129,0.35)',
            }}
          >
            <Zap size={14} />
            <span>Launch 1-Click Outreach Hub ({uncontactedZeroWebLeads.length})</span>
          </button>
        </div>
      )}

      {/* ── How it works banner ── */}
      <div
        className="rounded-xl px-5 py-3.5 flex items-start gap-4 text-sm"
        style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)' }}
      >
        <div className="text-indigo-400 mt-0.5 flex-shrink-0">
          <ScanSearch size={18} />
        </div>
        <div className="space-y-1">
          <p className="font-semibold text-indigo-300">How Discovery Works</p>
          <div className="text-slate-400 leading-relaxed grid sm:grid-cols-4 gap-x-6 gap-y-1">
            <span><span className="text-white font-medium">1. Create a Job</span> — enter keywords e.g. "restaurants", set a city</span>
            <span><span className="text-sky-400 font-medium">🌐 DuckDuckGo</span> — finds businesses that already have websites (good for auditing)</span>
            <span><span className="text-amber-400 font-medium">📍 OpenStreetMap</span> — finds real physical businesses <em>without</em> websites — ideal sales leads</span>
            <span><span className="text-white font-medium">3. Target &amp; Audit</span> — filter by "No Website", click a business to trigger an audit</span>
          </div>
        </div>
      </div>

      {/* ── Filter Bar ── */}
      <GlassCard padding="sm">
        <div className="flex items-center gap-3 flex-wrap px-2 py-1">
          {/* Industry */}
          <SelectDropdown
            value={industry}
            onChange={setIndustry}
            options={INDUSTRIES}
            icon={<Building2 size={14} />}
          />

          {/* Country */}
          <SelectDropdown
            value={country}
            onChange={setCountry}
            options={COUNTRIES}
            icon={<Globe2 size={14} />}
          />

          {/* Round / Scan Batch Selector */}
          <div className="relative">
            <select
              value={selectedJobId}
              onChange={(e) => setSelectedJobId(e.target.value)}
              className="appearance-none pl-8 pr-7 py-2 rounded-lg border border-white/10 bg-white/5 text-xs font-medium text-slate-300 hover:border-white/20 focus:outline-none focus:border-indigo-500/50 transition-colors cursor-pointer max-w-[220px] truncate"
            >
              <option value="all" className="bg-slate-900 text-white">🎯 All Scan Batches ({allJobs.length})</option>
              {allJobs.map((j) => (
                <option key={j.id} value={j.id} className="bg-slate-900 text-white">
                  {j.name.length > 25 ? j.name.slice(0, 25) + '…' : j.name} ({j.found} leads)
                </option>
              ))}
            </select>
            <Briefcase size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-indigo-400 pointer-events-none" />
            <ChevronDown size={13} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          </div>

          {selectedJobId !== 'all' && (
            <button
              onClick={() => setSelectedJobId('all')}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 transition-all cursor-pointer"
              title="Reset scan round filter"
            >
              <span>Batch Filter Active</span>
              <X size={12} />
            </button>
          )}

          {/* Website tab filter */}
          <div
            className="flex items-center rounded-lg overflow-hidden border border-white/10"
            style={{ background: 'rgba(255,255,255,0.04)' }}
          >
            {([['all', 'All'], ['yes', 'Has Website'], ['no', 'No Website']] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setFilterWebsite(key)}
                className={`px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap ${filterWebsite === key ? 'bg-indigo-500/30 text-white' : 'text-slate-400 hover:text-white'}`}
              >
                {key === 'no' ? <span className="flex items-center gap-1"><AlertCircle size={11} />{label}</span>
                  : key === 'yes' ? <span className="flex items-center gap-1"><CheckCircle size={11} />{label}</span>
                  : label}
              </button>
            ))}
          </div>

          {/* Email / WhatsApp checkboxes */}
          <div className="flex items-center gap-1 rounded-lg border border-white/10 px-1" style={{ background: 'rgba(255,255,255,0.04)' }}>
            <label className={`flex items-center gap-1.5 px-2.5 py-2 cursor-pointer rounded-md transition-colors select-none text-xs font-medium ${filterEmail ? 'text-blue-300' : 'text-slate-400 hover:text-white'}`}>
              <input
                type="checkbox"
                checked={filterEmail}
                onChange={e => setFilterEmail(e.target.checked)}
                className="accent-blue-500 w-3.5 h-3.5"
              />
              <Mail size={12} />
              Has Email
            </label>
            <div className="w-px h-5 bg-white/10" />
            <label className={`flex items-center gap-1.5 px-2.5 py-2 cursor-pointer rounded-md transition-colors select-none text-xs font-medium ${filterWhatsApp ? 'text-green-300' : 'text-slate-400 hover:text-white'}`}>
              <input
                type="checkbox"
                checked={filterWhatsApp}
                onChange={e => setFilterWhatsApp(e.target.checked)}
                className="accent-green-500 w-3.5 h-3.5"
              />
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
              WhatsApp
            </label>
          </div>

          {/* Search */}
          <div className="relative flex-1 min-w-[180px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            <input
              type="text"
              placeholder="Search businesses..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-lg border border-white/10 bg-white/5 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-colors"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* View toggle */}
          <div
            className="flex items-center rounded-lg overflow-hidden border border-white/10"
            style={{ background: 'rgba(255,255,255,0.04)' }}
          >
            <button
              onClick={() => setViewMode('grid')}
              className={`px-3 py-2 transition-colors ${viewMode === 'grid' ? 'bg-indigo-500/30 text-white' : 'text-slate-400 hover:text-white'}`}
            >
              <LayoutGrid size={15} />
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`px-3 py-2 transition-colors ${viewMode === 'table' ? 'bg-indigo-500/30 text-white' : 'text-slate-400 hover:text-white'}`}
            >
              <Table2 size={15} />
            </button>
          </div>
        </div>
      </GlassCard>

      {/* ── Stats Row ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Discovered"
          value={stats.total}
          icon={<Building2 size={18} />}
          iconColor="text-indigo-400"
          change={12}
        />
        <StatCard
          label="This Week"
          value={stats.thisWeek}
          icon={<TrendingUp size={18} />}
          iconColor="text-purple-400"
          change={8}
        />
        <StatCard
          label="With Websites"
          value={stats.withWeb}
          icon={<Globe size={18} />}
          iconColor="text-emerald-400"
          change={5}
        />
        <StatCard
          label="Without Websites"
          value={stats.withoutWeb}
          icon={<AlertCircle size={18} />}
          iconColor="text-amber-400"
          change={14}
        />
      </div>

      {/* ── Job History Table ── */}
      <GlassCard padding="none">
        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          <div className="flex items-center gap-2">
            <Briefcase size={16} className="text-indigo-400" />
            <h2 className="font-semibold text-white text-sm">Job History</h2>
            <span className="ml-1 px-2 py-0.5 rounded-full text-xs font-medium" style={{ background: 'rgba(99,102,241,0.15)', color: '#818cf8' }}>
              {allJobs.length}
            </span>
          </div>
          <button className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors">
            <Filter size={13} />
            Filters
          </button>
        </div>

        {allJobs.length === 0 ? (
          <div className="py-16 flex flex-col items-center gap-3 text-center">
            <div className="w-14 h-14 rounded-2xl bg-indigo-500/10 flex items-center justify-center">
              <Search size={24} className="text-indigo-400" />
            </div>
            <p className="text-slate-300 font-medium">No discovery jobs yet</p>
            <p className="text-slate-500 text-sm">Start your first discovery to find businesses.</p>
            <button
              onClick={() => setShowNewJob(true)}
              className="mt-2 flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white"
              style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)' }}
            >
              <Plus size={15} />
              Start First Discovery
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  {['Job Name', 'Sources', 'Status', 'Progress', 'Found', 'Started', 'Duration', 'Actions'].map((col) => (
                    <th key={col} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allJobs.map((job, idx) => (
                  <motion.tr
                    key={job.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className="group hover:bg-white/3 transition-colors"
                    style={{ borderBottom: idx < allJobs.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}
                  >
                    <td className="px-5 py-3.5">
                      <span className="font-medium text-white">{job.name}</span>
                      <p className="text-xs text-slate-500 mt-0.5">{job.industry} · {job.country}</p>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex flex-wrap gap-1">
                        {job.sources.map((s) => (
                          <span key={s} className="px-1.5 py-0.5 rounded text-xs" style={{ background: 'rgba(99,102,241,0.12)', color: '#a5b4fc' }}>
                            {s}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-5 py-3.5">{statusBadge(job.status)}</td>
                    <td className="px-5 py-3.5 min-w-[120px]">
                      <ProgressBar value={job.progress} size="sm" color="auto" animate={false} />
                      <p className="text-xs text-slate-500 mt-1">{job.progress}%</p>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="font-semibold text-white">{job.found.toLocaleString()}</span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-400 text-xs whitespace-nowrap">{job.started}</td>
                    <td className="px-5 py-3.5 text-slate-400 text-xs">{job.duration}</td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          title="View Leads from this Batch"
                          onClick={() => setSelectedJobId(job.id)}
                          className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                            selectedJobId === job.id
                              ? 'text-indigo-300 bg-indigo-500/20'
                              : 'text-slate-400 hover:text-indigo-400 hover:bg-indigo-500/10'
                          }`}
                        >
                          <Eye size={14} />
                        </button>
                        {job.status === 'completed' && (
                          <button
                            title="Export Report (PDF)"
                            onClick={() => exportApi.downloadPdf({ discovery_job_id: job.id }, job.name).catch(() => {})}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-400 hover:bg-indigo-500/10 transition-colors"
                          >
                            <Download size={14} />
                          </button>
                        )}
                        <button
                          title="Re-run"
                          onClick={() => rerunMutation.mutate(job.id)}
                          disabled={rerunMutation.isPending}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors disabled:opacity-40"
                        >
                          <Play size={14} />
                        </button>
                        <button
                          title="Delete"
                          onClick={() => setDeletingJobId(job.id)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      {/* ── Results Grid / Table ── */}
      <div>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Building2 size={16} className="text-purple-400" />
            <h2 className="font-semibold text-white text-sm">Discovered Businesses</h2>
            <span className="ml-1 px-2 py-0.5 rounded-full text-xs font-medium" style={{ background: 'rgba(168,85,247,0.15)', color: '#c084fc' }}>
              {filteredBusinesses.length}
            </span>
            {selectedJobId !== 'all' && (
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center gap-1.5">
                <span>Batch: {allJobs.find(j => j.id === selectedJobId)?.name || 'Selected'}</span>
                <button onClick={() => setSelectedJobId('all')} className="hover:text-white cursor-pointer"><X size={11} /></button>
              </span>
            )}
            <span className="text-xs text-slate-500">— businesses are kept even if you delete a job</span>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {filterWebsite === 'all' && stats.withoutWeb > 0 && (
              <button
                onClick={() => setFilterWebsite('no')}
                className="flex items-center gap-1.5 text-xs font-medium text-amber-400 hover:text-amber-300 transition-colors mr-1"
              >
                <AlertCircle size={13} />
                {stats.withoutWeb} without website — click to target these
              </button>
            )}

            {filteredBusinesses.length > 0 && (
              <button
                onClick={() => setShowClearConfirm(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 transition-all cursor-pointer"
                title={selectedJobId !== 'all' ? "Delete all leads from this round" : "Clear all discovered leads"}
              >
                <Trash2 size={13} />
                <span>{selectedJobId !== 'all' ? `Wipe Round Leads (${filteredBusinesses.length})` : `Clear Leads (${filteredBusinesses.length})`}</span>
              </button>
            )}
          </div>
        </div>

        {filteredBusinesses.length === 0 ? (
          <GlassCard>
            <div className="py-12 flex flex-col items-center gap-3 text-center">
              <Building2 size={32} className="text-slate-600" />
              <p className="text-slate-400 font-medium">No businesses match your filters</p>
              <p className="text-slate-600 text-sm">Try adjusting the filters above.</p>
            </div>
          </GlassCard>
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredBusinesses.map((b, idx) => (
              <motion.div
                key={b.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.04 }}
              >
                <BusinessCard
                  business={b}
                  onClick={() => setSelectedBusiness(b)}
                  isSelected={selectedBusinessIds.has(b.id)}
                  onToggleSelect={(e) => toggleSelectBusiness(b.id, e)}
                  onDelete={(e) => handleDeleteSingleLead(b, e)}
                  isContacted={dealByBusinessId.get(b.id)?.stage === 'contacted'}
                  onQuickWhatsApp={(e) => handleQuickWhatsApp(b, e)}
                  onQuickInstagram={(e) => handleQuickInstagram(b, e)}
                />
              </motion.div>
            ))}
          </div>
        ) : (
          <GlassCard padding="none">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <th className="px-4 py-3 w-10 text-center">
                      <input
                        type="checkbox"
                        checked={filteredBusinesses.length > 0 && selectedBusinessIds.size === filteredBusinesses.length}
                        onChange={(e) => toggleSelectAll(e.target.checked)}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 accent-indigo-500 cursor-pointer"
                        title="Select All"
                      />
                    </th>
                    {['Business', 'Industry', 'Location', 'Website', 'Score', 'Outreach', 'Source', 'Discovered', 'Actions'].map((col) => (
                      <th key={col} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredBusinesses.map((b, idx) => (
                    <motion.tr
                      key={b.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: idx * 0.03 }}
                      onClick={() => setSelectedBusiness(b)}
                      className={`group hover:bg-white/3 transition-colors cursor-pointer ${
                        selectedBusinessIds.has(b.id) ? 'bg-indigo-500/10' : ''
                      }`}
                      style={{ borderBottom: idx < filteredBusinesses.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}
                    >
                      <td className="px-4 py-3.5 text-center" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selectedBusinessIds.has(b.id)}
                          onChange={() => {}}
                          onClick={(e) => toggleSelectBusiness(b.id, e)}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 accent-indigo-500 cursor-pointer"
                        />
                      </td>
                      <td className="px-5 py-3.5 font-medium text-white group-hover:text-indigo-300 transition-colors">{b.name}</td>
                      <td className="px-5 py-3.5">
                        <Badge variant={industryColor(b.industry) as any} size="sm">{b.industry}</Badge>
                      </td>
                      <td className="px-5 py-3.5 text-slate-400 text-xs">{b.city}, {b.country}</td>
                      <td className="px-5 py-3.5">
                        {b.source === 'reddit' ? (
                          <span className="flex items-center gap-1 text-xs text-orange-400 font-medium"><Briefcase size={12} /> Client Lead</span>
                        ) : ['freelance', 'upwork', 'freelancer', 'fiverr'].includes(b.source?.toLowerCase()) ? (
                          <span className="flex items-center gap-1 text-xs text-emerald-400 font-medium"><Briefcase size={12} /> Hiring Job</span>
                        ) : b.hasWebsite ? (
                          <span className="flex items-center gap-1 text-xs text-emerald-400"><CheckCircle size={12} /> Yes</span>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-amber-400"><AlertCircle size={12} /> No</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        <ScoreRing score={b.opportunityScore} size={36} strokeWidth={3} showValue animate={false} />
                      </td>
                      <td className="px-5 py-3.5" onClick={(e) => e.stopPropagation()}>
                        {['freelance', 'upwork', 'freelancer', 'fiverr'].includes(b.source?.toLowerCase()) ? (
                          <button
                            onClick={() => setSelectedBusiness(b)}
                            className="px-2 py-1 text-[11px] font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-md transition-all flex items-center gap-1 cursor-pointer"
                            title="Open Proposal & Job Post"
                          >
                            <Briefcase size={10} /> View Job
                          </button>
                        ) : !b.hasWebsite ? (
                          dealByBusinessId.get(b.id)?.stage === 'contacted' ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-purple-300 bg-purple-500/15 px-2 py-0.5 rounded-full border border-purple-500/30">
                              <CheckCircle2 size={11} className="text-purple-400" /> Contacted
                            </span>
                          ) : (
                            <div className="flex items-center gap-1.5">
                              {toWhatsAppUrl(b.phone, '') && (
                                <button
                                  onClick={(e) => handleQuickWhatsApp(b, e)}
                                  className="px-2 py-1 text-[11px] font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-md transition-all flex items-center gap-1 cursor-pointer"
                                  title="1-Click WhatsApp Pitch"
                                >
                                  <Phone size={10} /> WA
                                </button>
                              )}
                              {(b.source === 'instagram' || b.instagramUrl) && (
                                <button
                                  onClick={(e) => handleQuickInstagram(b, e)}
                                  className="px-2 py-1 text-[11px] font-semibold text-white bg-pink-600 hover:bg-pink-500 rounded-md transition-all flex items-center gap-1 cursor-pointer"
                                  title="1-Click Instagram DM Pitch"
                                >
                                  <Instagram size={10} /> DM
                                </button>
                              )}
                            </div>
                          )
                        ) : (
                          <span className="text-slate-600 text-xs">—</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        <SourceBadge source={b.source} />
                      </td>
                      <td className="px-5 py-3.5 text-slate-500 text-xs">{b.discoveredAt}</td>
                      <td className="px-5 py-3.5" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={(e) => handleDeleteSingleLead(b, e)}
                          title="Delete Lead"
                          className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100 cursor-pointer"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        )}
      </div>

      {/* ── 1-Click Rapid Outreach Hub Modal ── */}
      {showOutreachHub && (
        <RapidOutreachHubModal
          leads={uncontactedZeroWebLeads}
          dealByBusinessId={dealByBusinessId}
          onClose={() => setShowOutreachHub(false)}
          onMarkContacted={handleMarkContacted}
          onDeleteLead={async (leadId) => {
            await businessesApi.delete(leadId);
            queryClient.invalidateQueries({ queryKey: ['businesses'] });
            queryClient.invalidateQueries({ queryKey: ['crm', 'deals'] });
          }}
        />
      )}

      {/* ── New Job Modal ── */}
      {showNewJob && <NewJobModal onClose={() => setShowNewJob(false)} />}

      {/* ── Import Modal ── */}
      {showImport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)' }}>
          <div className="w-full max-w-2xl rounded-2xl p-6 space-y-5" style={{ background: 'rgba(14,14,32,0.98)', border: '1px solid rgba(255,255,255,0.1)' }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <FileText size={20} className="text-indigo-400" />
                <h2 className="text-lg font-bold text-white">Import Business List</h2>
              </div>
              <button onClick={() => { setShowImport(false); setImportStatus(null); setImportText(''); }} className="text-slate-400 hover:text-white"><X size={20} /></button>
            </div>
            <p className="text-sm text-slate-400">Paste one business per line. Format: <span className="text-slate-300 font-mono text-xs">Name | Email | Phone | City | Country | Industry</span></p>
            <p className="text-xs text-slate-500">Only Name is required. Example:<br/>
              <span className="font-mono text-slate-400">Rick Ramos Boxing | RickRamosBoxing@gmail.com | | Chicago | US | fitness</span>
            </p>
            <textarea
              value={importText}
              onChange={e => setImportText(e.target.value)}
              rows={10}
              placeholder={"Rick Ramos Boxing | RickRamosBoxing@gmail.com | | Chicago | US | fitness\nForm Follows Fitness | FormFollowsFitness@gmail.com | | Chicago | US | fitness"}
              className="w-full rounded-lg px-4 py-3 text-sm text-slate-200 font-mono placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 resize-none"
              style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
            />
            {importStatus && (
              <div className={`text-sm px-3 py-2 rounded-lg ${importStatus.startsWith('Error') ? 'text-red-300 bg-red-500/10' : 'text-green-300 bg-green-500/10'}`}>
                {importStatus}
              </div>
            )}
            <div className="flex justify-end gap-3">
              <button onClick={() => { setShowImport(false); setImportStatus(null); setImportText(''); }} className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">Cancel</button>
              <button
                onClick={async () => {
                  const lines = importText.trim().split('\n').filter(l => l.trim());
                  if (!lines.length) return;
                  const businesses = lines.map(line => {
                    const parts = line.split('|').map(p => p.trim());
                    return {
                      name: parts[0] || '',
                      email: parts[1] || undefined,
                      phone: parts[2] || undefined,
                      city: parts[3] || undefined,
                      country: parts[4] || 'United States',
                      industry: parts[5] || undefined,
                    };
                  }).filter(b => b.name);
                  try {
                    const token = localStorage.getItem('bi_access_token');
                    const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000') + '/api/v1';
                    const res = await fetch(`${apiBase}/businesses/bulk-import`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                      body: JSON.stringify({ businesses }),
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || 'Import failed');
                    setImportStatus(`✓ Imported ${data.created} businesses (${data.skipped} skipped as duplicates)`);
                    queryClient.invalidateQueries({ queryKey: ['businesses'] });
                  } catch (e: unknown) {
                    setImportStatus(`Error: ${(e as Error).message}`);
                  }
                }}
                className="px-5 py-2 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90"
                style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)' }}
              >
                Import {importText.trim().split('\n').filter(l => l.trim()).length} businesses
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Business Detail Modal ── */}
      {selectedBusiness && (
        <BusinessDetailModal
          business={selectedBusiness}
          onClose={() => setSelectedBusiness(null)}
          onTriggerAudit={handleTriggerAudit}
          onDelete={(b) => handleDeleteSingleLead(b)}
        />
      )}

      {/* ── Floating Bulk Action Toolbar ── */}
      <AnimatePresence>
        {selectedBusinessIds.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 30 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 px-5 py-3 rounded-2xl border border-white/20 shadow-2xl backdrop-blur-xl"
            style={{
              background: 'rgba(15, 15, 35, 0.96)',
              boxShadow: '0 20px 50px rgba(0,0,0,0.8), 0 0 30px rgba(99,102,241,0.25)',
            }}
          >
            <div className="flex items-center gap-2 pr-2 border-r border-white/10 text-xs font-bold text-white">
              <span className="w-6 h-6 rounded-lg bg-indigo-500/30 text-indigo-300 flex items-center justify-center font-bold text-xs">
                {selectedBusinessIds.size}
              </span>
              <span>Leads Selected</span>
            </div>

            <button
              onClick={handleBulkDelete}
              disabled={bulkDeleting}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl font-bold text-xs text-white bg-red-600 hover:bg-red-500 transition-all shadow-md active:scale-95 cursor-pointer disabled:opacity-50"
            >
              <Trash2 size={13} />
              <span>{bulkDeleting ? 'Deleting...' : `Delete Selected (${selectedBusinessIds.size})`}</span>
            </button>

            <button
              onClick={() => {
                const selected = filteredBusinesses.filter((b) => selectedBusinessIds.has(b.id));
                const headers = ['Name', 'Industry', 'City', 'Country', 'Phone', 'Email', 'Source', 'Discovered'];
                const rows = selected.map((b) => [b.name, b.industry, b.city, b.country, b.phone || '', b.email || '', b.source, b.discoveredAt]);
                const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.map(c => `"${(c||'').replace(/"/g, '""')}"`).join(','))].join('\n');
                const link = document.createElement('a');
                link.setAttribute('href', encodeURI(csvContent));
                link.setAttribute('download', `leads_export_${Date.now()}.csv`);
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
              }}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl font-semibold text-xs text-slate-300 hover:text-white bg-white/5 hover:bg-white/10 transition-all border border-white/10 cursor-pointer"
            >
              <Download size={13} />
              <span>Export CSV</span>
            </button>

            <button
              onClick={() => setSelectedBusinessIds(new Set())}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white transition-colors cursor-pointer"
              title="Deselect All"
            >
              <X size={15} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Clear / Wipe Leads Confirmation Modal ── */}
      <AnimatePresence>
        {showClearConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}
            onClick={() => setShowClearConfirm(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="w-full max-w-md rounded-2xl p-6 space-y-4"
              style={{
                background: 'rgba(14,14,32,0.98)',
                border: '1px solid rgba(239,68,68,0.3)',
                boxShadow: '0 40px 80px rgba(0,0,0,0.8), 0 0 30px rgba(239,68,68,0.15)',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center text-red-400">
                  <Trash2 size={20} />
                </div>
                <div>
                  <h3 className="font-bold text-white text-base">
                    Delete {filteredBusinesses.length} Leads?
                  </h3>
                  <p className="text-xs text-slate-400">This action cannot be undone.</p>
                </div>
              </div>

              <p className="text-xs text-slate-300 leading-relaxed">
                {selectedJobId !== 'all'
                  ? `Permanently delete all ${filteredBusinesses.length} leads in this scan round, including their associated CRM deals and activity history.`
                  : `Permanently delete all ${filteredBusinesses.length} currently filtered leads and remove their associated CRM deals.`}
              </p>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  onClick={() => setShowClearConfirm(false)}
                  className="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:text-white bg-white/5 border border-white/10 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmClear}
                  disabled={clearingLeads}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-white bg-red-600 hover:bg-red-500 transition-all shadow-lg shadow-red-600/30 active:scale-95 disabled:opacity-50 cursor-pointer"
                >
                  {clearingLeads ? 'Deleting...' : 'Yes, Delete Leads'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Delete Confirmation Modal ── */}
      <AnimatePresence>
        {deletingJobId && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}
            onClick={() => setDeletingJobId(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="w-full max-w-sm rounded-2xl p-6"
              style={{
                background: 'rgba(14,14,32,0.97)',
                border: '1px solid rgba(255,255,255,0.1)',
                boxShadow: '0 40px 80px rgba(0,0,0,0.6)',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center">
                  <Trash2 size={18} className="text-red-400" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">Delete Job</h3>
                  <p className="text-xs text-slate-400">This action cannot be undone.</p>
                </div>
              </div>
              <p className="text-sm text-slate-400 mb-6">
                Are you sure you want to delete this discovery job? All associated results will be removed.
              </p>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setDeletingJobId(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm text-slate-400 hover:text-white hover:bg-white/8 transition-colors border border-white/10"
                >
                  Cancel
                </button>
                <button
                  onClick={() => deleteMutation.mutate(deletingJobId!)}
                  disabled={deleteMutation.isPending}
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 transition-colors disabled:opacity-50"
                >
                  {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
