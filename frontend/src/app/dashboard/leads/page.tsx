'use client';

import React, { useState, useMemo, useCallback } from 'react';

function toWhatsAppUrl(phone: string | null | undefined, text: string): string | null {
  if (!phone) return null;
  const digits = phone.replace(/\D/g, '');
  if (digits.length < 7) return null;
  if (digits.startsWith('1') && digits.length === 11) return null;
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
}
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { businessesApi, exportApi, proposalsApi, crmApi, outreachApi } from '@/lib/api';
import type { BusinessRaw } from '@/lib/api';
import {
  Target,
  Download,
  FileText,
  Globe,
  Smartphone,
  Monitor,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  ExternalLink,
  Plus,
  X,
  Building2,
  MapPin,
  DollarSign,
  Zap,
  Eye,
  Filter,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  Search,
  Star,
  TrendingUp,
  Mail,
  Phone,
  FileSpreadsheet,
  Share2,
  Layers,
  Award,
  BarChart2,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import { cn, formatCurrency, getScoreColor } from '@/lib/utils';
import GlassCard from '@/components/ui/GlassCard';
import Badge from '@/components/ui/Badge';
import ProgressBar from '@/components/ui/ProgressBar';

// ─── Types ──────────────────────────────────────────────────────────────────

interface LeadBusiness {
  id: string;
  rank: number;
  rankMovement: number; // positive = up, negative = down, 0 = same
  name: string;
  city: string;
  country: string;
  industry: string;
  website: string | null;
  hasWebsite: boolean;
  opportunityScore: number;
  seoScore: number;
  mobileScore: number;
  uiScore: number;
  priorityScore: number;
  revenuePotentialMin: number;
  revenuePotentialMax: number;
  opportunities: string[];
  primaryOpportunity: string;
  email: string | null;
  phone: string | null;
  whatsapp: string | null;
  email2: string | null;
  phone2: string | null;
  facebookUrl: string | null;
  instagramUrl: string | null;
  linkedinUrl: string | null;
  twitterUrl: string | null;
  tiktokUrl: string | null;
  youtubeUrl: string | null;
  completenessScore: number;
  aiAnalysis: string;
  recommendations: { title: string; value: number; description: string }[];
  discoveredAt: string;
}

// ─── Map backend business to LeadBusiness ────────────────────────────────────

function businessToLead(b: BusinessRaw, rank: number): LeadBusiness {
  const actualHasWebsite = Boolean(b.has_website && b.website_url && b.website_url.trim());
  const opps: string[] = [];
  if (!actualHasWebsite) opps.push('New Website');
  else opps.push('SEO');
  if (b.overall_score != null && b.overall_score < 50) opps.push('Redesign');
  if (opps.length < 2) opps.push('Optimization');

  return {
    id: b.id,
    rank,
    rankMovement: 0,
    name: b.name,
    city: b.city ?? '',
    country: b.country ?? '',
    industry: b.industry ?? b.category ?? 'Unknown',
    website: actualHasWebsite ? b.website_url : null,
    hasWebsite: actualHasWebsite,
    opportunityScore: b.opportunity_score ?? 0,
    seoScore: b.overall_score ?? 0,
    mobileScore: b.overall_score ?? 0,
    uiScore: b.overall_score ?? 0,
    priorityScore: b.priority_score ?? b.opportunity_score ?? 0,
    revenuePotentialMin: b.revenue_potential ? Math.round(b.revenue_potential * 0.7) : 0,
    revenuePotentialMax: b.revenue_potential ?? 0,
    opportunities: opps,
    primaryOpportunity: opps[0] ?? 'Optimization',
    email: b.email,
    phone: b.phone,
    whatsapp: b.whatsapp ?? null,
    email2: b.email2 ?? null,
    phone2: b.phone2 ?? null,
    facebookUrl: b.facebook_url ?? null,
    instagramUrl: b.instagram_url ?? null,
    linkedinUrl: b.linkedin_url ?? null,
    twitterUrl: b.twitter_url ?? null,
    tiktokUrl: b.tiktok_url ?? null,
    youtubeUrl: b.youtube_url ?? null,
    completenessScore: b.completeness_score ?? 0,
    aiAnalysis: b.description ?? 'No AI analysis available yet.',
    recommendations: [],
    discoveredAt: b.discovered_at ?? b.created_at,
  };
}

// ─── Completeness Badge ──────────────────────────────────────────────────────

function CompletenessBadge({ score }: { score: number }) {
  const rounded = Math.round(score);
  const { bg, text, border } =
    rounded >= 80
      ? { bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/30' }
      : rounded >= 50
      ? { bg: 'bg-amber-500/15', text: 'text-amber-400', border: 'border-amber-500/30' }
      : { bg: 'bg-red-500/15', text: 'text-red-400', border: 'border-red-500/30' };
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border', bg, text, border)}>
      {rounded}% complete
    </span>
  );
}

// ─── Score Bar Component ─────────────────────────────────────────────────────

function MiniScoreBar({ label, value }: { label: string; value: number }) {
  const color =
    value >= 70 ? 'bg-emerald-500' : value >= 40 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="text-xs text-slate-500 w-10 flex-shrink-0">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', color)}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="text-xs text-slate-400 w-6 flex-shrink-0 text-right">{value}</span>
    </div>
  );
}

// ─── Rank Movement Indicator ─────────────────────────────────────────────────

function RankMovement({ value }: { value: number }) {
  if (value > 0)
    return (
      <span className="flex items-center gap-0.5 text-emerald-400 text-xs font-medium">
        <ArrowUpRight size={12} />+{value}
      </span>
    );
  if (value < 0)
    return (
      <span className="flex items-center gap-0.5 text-red-400 text-xs font-medium">
        <ArrowDownRight size={12} />{value}
      </span>
    );
  return (
    <span className="flex items-center gap-0.5 text-slate-500 text-xs">
      <Minus size={12} />
    </span>
  );
}

// ─── Opportunity Score Badge ─────────────────────────────────────────────────

function OpportunityBadge({ score }: { score: number }) {
  const { bg, text, shadow } =
    score >= 90
      ? { bg: 'bg-emerald-500/20', text: 'text-emerald-300', shadow: 'shadow-emerald-500/20' }
      : score >= 75
      ? { bg: 'bg-indigo-500/20', text: 'text-indigo-300', shadow: 'shadow-indigo-500/20' }
      : score >= 60
      ? { bg: 'bg-amber-500/20', text: 'text-amber-300', shadow: 'shadow-amber-500/20' }
      : { bg: 'bg-red-500/20', text: 'text-red-300', shadow: 'shadow-red-500/20' };

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center w-12 h-12 rounded-xl text-lg font-bold border',
        bg,
        text,
        score >= 90
          ? 'border-emerald-500/30'
          : score >= 75
          ? 'border-indigo-500/30'
          : score >= 60
          ? 'border-amber-500/30'
          : 'border-red-500/30',
        shadow,
        'shadow-lg'
      )}
    >
      {score}
    </span>
  );
}

// ─── Leaderboard Card ────────────────────────────────────────────────────────

interface LeaderboardCardProps {
  lead: LeadBusiness;
  position: 1 | 2 | 3;
  onClick: () => void;
}

const RANK_CONFIG = {
  1: {
    gradient: 'linear-gradient(135deg, rgba(251,191,36,0.15), rgba(245,158,11,0.05))',
    border: 'rgba(251,191,36,0.3)',
    badge: 'linear-gradient(135deg, #f59e0b, #fbbf24)',
    glow: 'rgba(251,191,36,0.2)',
    label: '#1',
    crown: '👑',
  },
  2: {
    gradient: 'linear-gradient(135deg, rgba(148,163,184,0.15), rgba(100,116,139,0.05))',
    border: 'rgba(148,163,184,0.3)',
    badge: 'linear-gradient(135deg, #94a3b8, #cbd5e1)',
    glow: 'rgba(148,163,184,0.15)',
    label: '#2',
    crown: '🥈',
  },
  3: {
    gradient: 'linear-gradient(135deg, rgba(180,120,60,0.15), rgba(146,64,14,0.05))',
    border: 'rgba(180,120,60,0.3)',
    badge: 'linear-gradient(135deg, #b45309, #d97706)',
    glow: 'rgba(180,120,60,0.15)',
    label: '#3',
    crown: '🥉',
  },
};

function LeaderboardCard({ lead, position, onClick }: LeaderboardCardProps) {
  const config = RANK_CONFIG[position];

  return (
    <motion.div
      whileHover={{ y: -4, boxShadow: `0 24px 48px rgba(0,0,0,0.5), 0 0 30px ${config.glow}` }}
      transition={{ duration: 0.2 }}
      onClick={onClick}
      className="relative rounded-2xl overflow-hidden cursor-pointer"
      style={{
        background: config.gradient,
        border: `1px solid ${config.border}`,
        boxShadow: `0 12px 32px rgba(0,0,0,0.4), 0 0 20px ${config.glow}`,
        backdropFilter: 'blur(16px)',
      }}
    >
      {/* Rank Badge */}
      <div
        className="absolute top-4 right-4 w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold text-white shadow-lg"
        style={{ background: config.badge }}
      >
        {position}
      </div>

      <div className="p-6">
        {/* Crown + Name */}
        <div className="mb-4">
          <div className="text-2xl mb-1">{config.crown}</div>
          <h3 className="text-lg font-bold text-white leading-tight">{lead.name}</h3>
          <div className="flex items-center gap-1.5 mt-1">
            <MapPin size={12} className="text-slate-400" />
            <span className="text-sm text-slate-400">{lead.city}</span>
            <span className="text-slate-600">·</span>
            <span className="text-xs text-slate-500 bg-white/5 px-2 py-0.5 rounded-full">{lead.industry}</span>
          </div>
        </div>

        {/* Score */}
        <div className="mb-4">
          <div className="text-5xl font-black text-white leading-none mb-1">
            {lead.opportunityScore}
          </div>
          <div className="text-xs text-slate-400 uppercase tracking-wider">Opportunity Score</div>
        </div>

        {/* Revenue */}
        <div className="mb-4 p-3 rounded-xl" style={{ background: 'rgba(0,0,0,0.2)' }}>
          <div className="text-xs text-slate-500 mb-1">Revenue Potential</div>
          <div className="text-base font-semibold text-white">
            {formatCurrency(lead.revenuePotentialMin)} – {formatCurrency(lead.revenuePotentialMax)}
          </div>
        </div>

        {/* Primary Opportunity */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">Top Opportunity</span>
          <span
            className="text-xs font-semibold px-2.5 py-1 rounded-full"
            style={{ background: config.badge, color: 'white' }}
          >
            {lead.primaryOpportunity}
          </span>
        </div>
      </div>

      {/* Bottom Gradient Line */}
      <div
        className="absolute bottom-0 left-0 right-0 h-0.5"
        style={{ background: `linear-gradient(90deg, transparent, ${config.border}, transparent)` }}
      />
    </motion.div>
  );
}

// ─── Expanded Row Detail ─────────────────────────────────────────────────────

function ExpandedRow({ lead }: { lead: LeadBusiness }) {
  return (
    <div
      className="px-6 py-5 border-t border-white/5"
      style={{ background: 'rgba(10,10,25,0.4)' }}
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* AI Analysis */}
        <div className="md:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={14} className="text-indigo-400" />
            <span className="text-sm font-semibold text-slate-300">AI Analysis</span>
          </div>
          <p className="text-sm text-slate-400 leading-relaxed">{lead.aiAnalysis}</p>
        </div>

        {/* Scores Detail */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <BarChart2 size={14} className="text-purple-400" />
            <span className="text-sm font-semibold text-slate-300">Audit Scores</span>
          </div>
          <div className="space-y-3">
            <MiniScoreBar label="SEO" value={lead.seoScore} />
            <MiniScoreBar label="Mobile" value={lead.mobileScore} />
            <MiniScoreBar label="UI/UX" value={lead.uiScore} />
            <div className="pt-2 border-t border-white/10">
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">Priority Score</span>
                <span className="text-slate-300 font-semibold">{lead.priorityScore}/100</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Business Profile Panel ──────────────────────────────────────────────────

interface ProfilePanelProps {
  lead: LeadBusiness;
  onClose: () => void;
}

function ScoreRow({ label, value, icon }: { label: string; value: number | null; icon: React.ReactNode }) {
  const v = value ?? 0;
  const color = v >= 70 ? 'text-emerald-400' : v >= 40 ? 'text-amber-400' : v > 0 ? 'text-red-400' : 'text-slate-600';
  const barColor = v >= 70 ? 'bg-emerald-500' : v >= 40 ? 'bg-amber-500' : v > 0 ? 'bg-red-500' : 'bg-slate-700';
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <span className="text-slate-500">{icon}</span>
          {label}
        </div>
        <span className={cn('text-xs font-bold', color)}>{v > 0 ? `${v}/100` : 'N/A'}</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className={cn('h-full rounded-full transition-all duration-700', barColor)} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

function BusinessProfilePanel({ lead, onClose }: ProfilePanelProps) {
  const queryClient = useQueryClient();
  const [actionMsg, setActionMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showOutreach, setShowOutreach] = useState(false);

  const { data: business } = useQuery({
    queryKey: ['business-detail', lead.id],
    queryFn: () => businessesApi.get(lead.id),
  });

  const { data: auditsData } = useQuery({
    queryKey: ['business-audits', lead.id],
    queryFn: () => businessesApi.getAudits(lead.id),
  });

  // Generate Proposal
  const proposalMutation = useMutation({
    mutationFn: () => proposalsApi.generate({ business_id: lead.id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals'] });
      setActionMsg({ type: 'success', text: 'Proposal generated! View it in the Proposals page.' });
      setTimeout(() => setActionMsg(null), 4000);
    },
    onError: () => setActionMsg({ type: 'error', text: 'Failed to generate proposal. Run an audit first.' }),
  });

  // Add to CRM — auto-creates a pipeline if none exists
  const crmMutation = useMutation({
    mutationFn: async () => {
      let pipelines = await crmApi.listPipelines();
      if (pipelines.length === 0) {
        const p = await crmApi.createPipeline({ name: 'Sales Pipeline', is_default: true });
        pipelines = [p];
      }
      return crmApi.createDeal({
        business_id: lead.id,
        pipeline_id: pipelines[0].id,
        title: lead.name,
        stage: 'lead',
        value: lead.revenuePotentialMax || 0,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-deals'] });
      setActionMsg({ type: 'success', text: 'Added to CRM as a new lead deal!' });
      setTimeout(() => setActionMsg(null), 4000);
    },
    onError: () => setActionMsg({ type: 'error', text: 'Failed to add to CRM.' }),
  });

  // Generate outreach email
  const outreachMutation = useMutation({
    mutationFn: () => outreachApi.generateEmail({ business_id: lead.id, sender_name: 'Our Team', template_type: 'initial_outreach', include_audit: true }),
    onSuccess: () => setShowOutreach(true),
  });

  // Send email directly via SMTP
  const sendEmailMutation = useMutation({
    mutationFn: () => {
      const emailData = outreachMutation.data!;
      const toEmail = business?.email ?? lead.email ?? '';
      if (!toEmail) throw new Error('No email address found for this business');
      return outreachApi.sendEmail({
        business_id: lead.id,
        to_email: toEmail,
        subject: emailData.subject,
        body_html: emailData.body_html,
        body_text: emailData.body_text,
      });
    },
    onSuccess: (data) => {
      setActionMsg({ type: 'success', text: `Email sent to ${data.to}!` });
      setTimeout(() => setActionMsg(null), 5000);
    },
    onError: (err: Error) => {
      const msg = err.message.includes('SMTP not configured')
        ? 'SMTP not configured — go to Settings → Email / SMTP to set it up.'
        : err.message || 'Failed to send email';
      setActionMsg({ type: 'error', text: msg });
      setTimeout(() => setActionMsg(null), 7000);
    },
  });

  const latestAudit = auditsData?.items?.[0] ?? null;

  const scores = latestAudit
    ? [
        { label: 'SEO', value: latestAudit.seo_score, icon: <Globe size={12} /> },
        { label: 'Mobile', value: latestAudit.mobile_score, icon: <Smartphone size={12} /> },
        { label: 'UI/UX', value: latestAudit.ui_score, icon: <Monitor size={12} /> },
        { label: 'Accessibility', value: latestAudit.accessibility_score, icon: <Eye size={12} /> },
        { label: 'Security', value: latestAudit.security_score, icon: <CheckCircle2 size={12} /> },
        { label: 'Speed', value: latestAudit.speed_score, icon: <Zap size={12} /> },
        { label: 'Content', value: latestAudit.content_score, icon: <FileText size={12} /> },
      ]
    : [
        { label: 'SEO', value: lead.seoScore, icon: <Globe size={12} /> },
        { label: 'Mobile', value: lead.mobileScore, icon: <Smartphone size={12} /> },
        { label: 'UI/UX', value: lead.uiScore, icon: <Monitor size={12} /> },
      ];

  const b = business;
  const websiteUrl = b?.website_url ?? lead.website;

  // tech_stack can be string[] or {name, category}[] — normalize to string[]
  const rawStack = latestAudit?.tech_stack ?? [];
  const techStack: string[] = (rawStack as unknown[]).map((t) =>
    typeof t === 'string' ? t : (t as { name: string }).name ?? ''
  ).filter(Boolean);

  // recommendations can be string[] or {title, description, ...}[] — normalize
  const rawRecs = latestAudit?.recommendations ?? [];
  const recommendations: Array<{ title: string; description: string; category?: string; priority?: string }> =
    (rawRecs as unknown[]).map((r) =>
      typeof r === 'string'
        ? { title: r.slice(0, 80), description: r }
        : (r as { title: string; description: string; category?: string; priority?: string })
    );

  // ai_analysis can be a string (old format) or a structured dict (new format)
  const rawAiAnalysis = latestAudit?.ai_analysis ?? null;
  const aiAnalysisText: string = typeof rawAiAnalysis === 'string'
    ? rawAiAnalysis
    : rawAiAnalysis
      ? (rawAiAnalysis as { executive_summary?: string }).executive_summary ?? 'Audit completed.'
      : b?.description ?? 'Run an audit to get AI analysis for this business.';

  const aiAnalysisStructured = rawAiAnalysis && typeof rawAiAnalysis === 'object'
    ? rawAiAnalysis as {
        executive_summary?: string;
        strengths?: string[];
        weaknesses?: string[];
        opportunities?: string[];
        estimated_value?: string;
      }
    : null;

  const seoIssues: Array<{ title?: string; description?: string; severity?: string }> = (latestAudit?.seo_issues as Array<{ title?: string; description?: string; severity?: string }>) ?? [];
  const perfMetrics: Record<string, unknown> = latestAudit?.performance_metrics ?? {};

  const overallScore = latestAudit?.overall_score ?? b?.overall_score ?? lead.opportunityScore;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ x: '100%', opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: '100%', opacity: 0 }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed right-0 top-0 bottom-0 w-full max-w-2xl z-50 overflow-y-auto"
        style={{
          background: 'rgba(10,10,24,0.98)',
          backdropFilter: 'blur(24px)',
          borderLeft: '1px solid rgba(255,255,255,0.08)',
          boxShadow: '-24px 0 64px rgba(0,0,0,0.7)',
        }}
      >
        {/* Header */}
        <div
          className="sticky top-0 z-10 px-6 py-4 border-b border-white/10"
          style={{ background: 'rgba(10,10,24,0.96)', backdropFilter: 'blur(20px)' }}
        >
          <div className="flex items-start justify-between">
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-bold text-white truncate">{lead.name}</h2>
              <div className="flex items-center gap-3 mt-1 flex-wrap">
                <span className="flex items-center gap-1 text-xs text-slate-400">
                  <MapPin size={11} /> {lead.city}{lead.country ? `, ${lead.country}` : ''}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-400 border border-indigo-500/20">
                  {lead.industry}
                </span>
                {lead.completenessScore > 0 && <CompletenessBadge score={lead.completenessScore} />}
                {websiteUrl && (
                  <a
                    href={websiteUrl.startsWith('http') ? websiteUrl : `https://${websiteUrl}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                  >
                    <ExternalLink size={11} /> {websiteUrl.replace(/^https?:\/\//, '').split('/')[0]}
                  </a>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/10 transition-colors ml-4 flex-shrink-0"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6">

          {/* Score Hero */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Overall Score', value: overallScore, color: 'text-indigo-300', bg: 'rgba(99,102,241,0.12)', border: 'rgba(99,102,241,0.2)' },
              { label: 'Opportunity', value: b?.opportunity_score ?? lead.opportunityScore, color: 'text-emerald-300', bg: 'rgba(16,185,129,0.10)', border: 'rgba(16,185,129,0.2)' },
              { label: 'Priority', value: b?.priority_score ?? lead.priorityScore, color: 'text-purple-300', bg: 'rgba(168,85,247,0.10)', border: 'rgba(168,85,247,0.2)' },
            ].map((s) => (
              <div key={s.label} className="text-center p-4 rounded-xl" style={{ background: s.bg, border: `1px solid ${s.border}` }}>
                <div className={cn('text-3xl font-black', s.color)}>{s.value ?? '—'}</div>
                <div className="text-xs text-slate-500 mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Business Info */}
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.07)' }}>
            <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
              <Building2 size={13} className="text-slate-400" />
              <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Business Details</span>
            </div>
            <div className="divide-y divide-white/5">
              {[
                { label: 'Website', value: websiteUrl, link: websiteUrl ? (websiteUrl.startsWith('http') ? websiteUrl : `https://${websiteUrl}`) : null },
                { label: 'Contact Page', value: b?.contact_page_url ?? null, link: b?.contact_page_url ?? null },
                { label: 'Email', value: b?.email ?? lead.email ?? null },
                { label: 'Email 2', value: b?.email2 ?? lead.email2 ?? null },
                { label: 'Phone', value: b?.phone ?? lead.phone ?? null },
                { label: 'Phone 2', value: b?.phone2 ?? lead.phone2 ?? null },
                { label: 'WhatsApp', value: b?.whatsapp ?? lead.whatsapp ?? null },
                { label: 'Address', value: b?.address ?? null },
                { label: 'Rating', value: b?.rating ? `${b.rating.toFixed(1)} / 5 (${b.review_count ?? 0} reviews)` : null },
                { label: 'Founded', value: b?.founded_year ? String(b.founded_year) : null },
                { label: 'Company Size', value: b?.company_size ?? null },
                { label: 'Source', value: b?.source ?? null },
                { label: 'Discovered', value: b?.discovered_at ? new Date(b.discovered_at).toLocaleDateString() : null },
                { label: 'Last Audited', value: b?.last_audited_at ? new Date(b.last_audited_at).toLocaleDateString() : null },
                { label: 'Completeness', value: b?.completeness_score != null ? `${Math.round(b.completeness_score)}%` : null },
              ]
                .filter((r) => r.value)
                .map((row) => (
                  <div key={row.label} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-xs text-slate-500 w-28 flex-shrink-0">{row.label}</span>
                    {row.link ? (
                      <a
                        href={row.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs font-medium text-emerald-400 hover:text-emerald-300 truncate flex items-center gap-1"
                      >
                        {row.value} <ExternalLink size={10} />
                      </a>
                    ) : (
                      <span className="text-xs font-medium text-slate-300 truncate text-right">{row.value}</span>
                    )}
                  </div>
                ))}
            </div>
          </div>

          {/* Social Media */}
          {(() => {
            const socials = [
              { label: 'Facebook', url: b?.facebook_url ?? lead.facebookUrl, color: '#1877F2' },
              { label: 'Instagram', url: b?.instagram_url ?? lead.instagramUrl, color: '#E4405F' },
              { label: 'LinkedIn', url: b?.linkedin_url ?? lead.linkedinUrl, color: '#0A66C2' },
              { label: 'X / Twitter', url: b?.twitter_url ?? lead.twitterUrl, color: '#000000' },
              { label: 'TikTok', url: b?.tiktok_url ?? lead.tiktokUrl, color: '#010101' },
              { label: 'YouTube', url: b?.youtube_url ?? null, color: '#FF0000' },
            ].filter(s => s.url);
            if (socials.length === 0) return null;
            return (
              <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.07)' }}>
                <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                  <Share2 size={13} className="text-slate-400" />
                  <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Social Media</span>
                  <span className="ml-auto text-xs text-slate-500">{socials.length} profiles found</span>
                </div>
                <div className="p-3 flex flex-wrap gap-2">
                  {socials.map(s => (
                    <a
                      key={s.label}
                      href={s.url!}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white hover:opacity-80 transition-opacity"
                      style={{ background: s.color + '22', border: `1px solid ${s.color}44` }}
                    >
                      <ExternalLink size={10} style={{ color: s.color }} />
                      <span style={{ color: s.color }}>{s.label}</span>
                    </a>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Revenue Potential */}
          {(b?.revenue_potential ?? lead.revenuePotentialMax) > 0 && (
            <div className="p-4 rounded-xl flex items-center justify-between" style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.15)' }}>
              <div className="flex items-center gap-2">
                <DollarSign size={16} className="text-emerald-400" />
                <span className="text-sm font-semibold text-slate-300">Revenue Potential</span>
              </div>
              <span className="text-lg font-black text-emerald-300">
                {formatCurrency(lead.revenuePotentialMin)} – {formatCurrency(lead.revenuePotentialMax)}
              </span>
            </div>
          )}

          {/* Audit Scores */}
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.07)' }}>
            <div className="px-4 py-2.5 flex items-center justify-between" style={{ background: 'rgba(255,255,255,0.04)' }}>
              <div className="flex items-center gap-2">
                <BarChart2 size={13} className="text-slate-400" />
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Audit Scores</span>
              </div>
              {latestAudit && (
                <span className="text-xs text-slate-500">
                  Last audit: {new Date(latestAudit.created_at).toLocaleDateString()}
                </span>
              )}
            </div>
            <div className="p-4 space-y-4">
              {scores.map((s) => (
                <ScoreRow key={s.label} label={s.label} value={s.value} icon={s.icon} />
              ))}
              {!latestAudit && (
                <p className="text-xs text-slate-500 text-center py-2">No audit run yet — trigger one from the Audit page</p>
              )}
            </div>
          </div>

          {/* Performance Metrics */}
          {latestAudit && Object.keys(perfMetrics).length > 0 && (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.07)' }}>
              <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <Zap size={13} className="text-amber-400" />
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Performance Metrics</span>
              </div>
              <div className="grid grid-cols-2 gap-px bg-white/5">
                {Object.entries(perfMetrics).slice(0, 6).map(([key, val]) => (
                  <div key={key} className="px-4 py-3" style={{ background: 'rgba(10,10,24,0.9)' }}>
                    <div className="text-xs text-slate-500 capitalize">{key.replace(/_/g, ' ')}</div>
                    <div className="text-sm font-semibold text-white mt-0.5">{String(val)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tech Stack */}
          {techStack.length > 0 && (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.07)' }}>
              <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <Layers size={13} className="text-cyan-400" />
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Tech Stack</span>
              </div>
              <div className="p-4 flex flex-wrap gap-2">
                {techStack.map((t) => (
                  <span key={t} className="text-xs px-2.5 py-1 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* SEO Issues */}
          {seoIssues.length > 0 && (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.07)' }}>
              <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <AlertCircle size={13} className="text-red-400" />
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">SEO Issues ({seoIssues.length})</span>
              </div>
              <div className="divide-y divide-white/5">
                {seoIssues.slice(0, 5).map((issue, i) => (
                  <div key={i} className="px-4 py-3 flex items-start gap-3">
                    <div className={cn('w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0',
                      issue.severity === 'critical' ? 'bg-red-500' :
                      issue.severity === 'high' ? 'bg-orange-500' :
                      issue.severity === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
                    )} />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-white">{issue.title ?? `Issue ${i + 1}`}</p>
                      {issue.description && <p className="text-xs text-slate-500 mt-0.5">{issue.description}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AI Analysis */}
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(99,102,241,0.15)' }}>
            <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(99,102,241,0.08)' }}>
              <Zap size={13} className="text-indigo-400" />
              <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">AI Analysis</span>
            </div>
            <div className="p-4 space-y-3">
              <p className="text-sm text-slate-400 leading-relaxed">{aiAnalysisText}</p>
              {aiAnalysisStructured && (
                <div className="grid grid-cols-1 gap-3 mt-2">
                  {aiAnalysisStructured.strengths && aiAnalysisStructured.strengths.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-emerald-400 mb-1">Strengths</p>
                      <ul className="space-y-1">
                        {aiAnalysisStructured.strengths.map((s, i) => (
                          <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                            <span className="text-emerald-500 mt-0.5">✓</span>{s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {aiAnalysisStructured.weaknesses && aiAnalysisStructured.weaknesses.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-red-400 mb-1">Issues Found</p>
                      <ul className="space-y-1">
                        {aiAnalysisStructured.weaknesses.map((w, i) => (
                          <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                            <span className="text-red-500 mt-0.5">✗</span>{w}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {aiAnalysisStructured.opportunities && aiAnalysisStructured.opportunities.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-amber-400 mb-1">Opportunities</p>
                      <ul className="space-y-1">
                        {aiAnalysisStructured.opportunities.map((o, i) => (
                          <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                            <span className="text-amber-500 mt-0.5">→</span>{o}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(16,185,129,0.15)' }}>
              <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: 'rgba(16,185,129,0.07)' }}>
                <TrendingUp size={13} className="text-emerald-400" />
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Recommendations</span>
              </div>
              <div className="divide-y divide-white/5">
                {recommendations.map((rec, i) => (
                  <div key={i} className="px-4 py-3 flex items-start gap-3">
                    <div className="w-5 h-5 rounded-full bg-emerald-500/15 text-emerald-400 flex items-center justify-center flex-shrink-0 text-xs font-bold">
                      {i + 1}
                    </div>
                    <div>
                      <p className="text-xs text-slate-200 font-medium leading-relaxed">{rec.title}</p>
                      {rec.description !== rec.title && (
                        <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{rec.description}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Feedback message */}
          {actionMsg && (
            <div className={`px-4 py-3 rounded-xl text-sm font-medium flex items-center gap-2 ${actionMsg.type === 'success' ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/25' : 'bg-red-500/15 text-red-300 border border-red-500/25'}`}>
              {actionMsg.type === 'success' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
              {actionMsg.text}
            </div>
          )}

          {/* Outreach email panel */}
          {showOutreach && outreachMutation.data && (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(99,102,241,0.2)' }}>
              <div className="px-4 py-2.5 flex items-center justify-between" style={{ background: 'rgba(99,102,241,0.08)' }}>
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2"><Mail size={12} className="text-indigo-400" /> Generated Email</span>
                <button onClick={() => setShowOutreach(false)} className="text-slate-500 hover:text-slate-300"><X size={13} /></button>
              </div>
              <div className="p-4 space-y-3">
                <div className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.04)' }}>
                  <p className="text-xs text-slate-500 mb-1">Subject</p>
                  <p className="text-sm font-semibold text-white">{outreachMutation.data.subject}</p>
                </div>
                <div className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.04)' }}>
                  <p className="text-xs text-slate-500 mb-2">Body</p>
                  <pre className="text-xs text-slate-300 whitespace-pre-wrap font-sans leading-relaxed max-h-36 overflow-y-auto">{outreachMutation.data.body_text}</pre>
                </div>
                {(() => {
                  const toEmail = business?.email ?? lead.email ?? '';
                  const toPhone = business?.phone ?? lead.phone ?? '';
                  const waText = encodeURIComponent(outreachMutation.data.body_text.slice(0, 1000));
                  const waUrl = toWhatsAppUrl(toPhone, outreachMutation.data.body_text.slice(0, 1000));
                  const gmailUrl = toEmail ? `https://mail.google.com/mail/?view=cm&to=${encodeURIComponent(toEmail)}&su=${encodeURIComponent(outreachMutation.data.subject)}&body=${encodeURIComponent(outreachMutation.data.body_text)}` : null;

                  if (toEmail) return (
                    <div className="flex gap-2">
                      <button
                        onClick={() => sendEmailMutation.mutate()}
                        disabled={sendEmailMutation.isPending}
                        className="flex items-center justify-center gap-2 flex-1 py-2.5 rounded-xl text-sm font-semibold text-white hover:opacity-90 transition-opacity disabled:opacity-60"
                        style={{ background: 'linear-gradient(135deg,#6366f1,#a855f7)' }}
                      >
                        {sendEmailMutation.isPending ? <><motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}><Mail size={13} /></motion.div> Sending…</> : <><Mail size={13} /> Send Direct</>}
                      </button>
                      <a href={gmailUrl!} target="_blank" rel="noopener noreferrer"
                        className="flex items-center justify-center gap-2 flex-1 py-2.5 rounded-xl text-sm font-semibold text-white hover:opacity-90 transition-opacity"
                        style={{ background: '#EA4335' }}>
                        <Mail size={13} /> Gmail
                      </a>
                      {waUrl && (
                        <a href={waUrl} target="_blank" rel="noopener noreferrer"
                          className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-semibold text-white hover:opacity-90 transition-opacity"
                          style={{ background: '#25D366' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                        </a>
                      )}
                    </div>
                  );

                  if (waUrl) return (
                    <div className="space-y-2">
                      <p className="text-xs text-amber-400/80 flex items-center gap-1">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                        No email found — sending via WhatsApp
                      </p>
                      <a href={waUrl} target="_blank" rel="noopener noreferrer"
                        className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-semibold text-white hover:opacity-90 transition-opacity"
                        style={{ background: '#25D366' }}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                        Send via WhatsApp
                      </a>
                    </div>
                  );

                  return <p className="text-xs text-slate-500 text-center py-1">No email or phone available for this business</p>;
                })()}
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="space-y-3 pt-2">
            <button
              onClick={() => proposalMutation.mutate()}
              disabled={proposalMutation.isPending}
              className="w-full py-3 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 flex items-center justify-center gap-2 disabled:opacity-60"
              style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 8px 24px rgba(99,102,241,0.3)' }}
            >
              {proposalMutation.isPending ? (
                <><motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}><FileText size={15} /></motion.div> Generating…</>
              ) : (
                <><FileText size={15} /> Generate Proposal</>
              )}
            </button>
            <div className={`grid gap-3 ${websiteUrl ? 'grid-cols-3' : 'grid-cols-2'}`}>
              <button
                onClick={() => crmMutation.mutate()}
                disabled={crmMutation.isPending}
                className="py-2.5 rounded-xl text-xs font-medium text-slate-300 hover:text-white hover:bg-white/10 transition-colors flex items-center justify-center gap-1.5 disabled:opacity-60"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
              >
                {crmMutation.isPending ? <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}><Plus size={13} /></motion.div> : <Plus size={13} />}
                {crmMutation.isSuccess ? 'Added!' : 'Add to CRM'}
              </button>
              <button
                onClick={() => { setShowOutreach(false); outreachMutation.mutate(); }}
                disabled={outreachMutation.isPending}
                className="py-2.5 rounded-xl text-xs font-medium text-slate-300 hover:text-white hover:bg-white/10 transition-colors flex items-center justify-center gap-1.5 disabled:opacity-60"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
              >
                {outreachMutation.isPending ? <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}><Mail size={13} /></motion.div> : <Mail size={13} />}
                {outreachMutation.isPending ? 'Generating…' : 'Outreach'}
              </button>
              {websiteUrl && (
                <a
                  href={websiteUrl.startsWith('http') ? websiteUrl : `https://${websiteUrl}`}
                  target="_blank" rel="noopener noreferrer"
                  className="py-2.5 rounded-xl text-xs font-medium text-slate-300 hover:text-white transition-colors flex items-center justify-center gap-1.5"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
                >
                  <ExternalLink size={13} /> Visit Site
                </a>
              )}
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

const INDUSTRIES = ['All', 'Finance', 'Healthcare', 'Real Estate', 'Restaurant', 'Legal', 'Automotive', 'Health & Wellness', 'Design'];
const SORT_OPTIONS = [
  { value: 'opportunityScore', label: 'Opportunity Score' },
  { value: 'revenuePotentialMax', label: 'Revenue Potential' },
  { value: 'priorityScore', label: 'Priority Score' },
];

export default function LeadsPage() {
  const [selectedLead, setSelectedLead] = useState<LeadBusiness | null>(null);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<'opportunityScore' | 'revenuePotentialMax' | 'priorityScore'>('opportunityScore');
  const [filterIndustry, setFilterIndustry] = useState('All');
  const [filterWebsite, setFilterWebsite] = useState<'All' | 'Yes' | 'No'>('All');
  const [scoreMin, setScoreMin] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);

  const handleExport = useCallback(async (format: 'csv' | 'excel' | 'pdf') => {
    setExportStatus(`Generating ${format.toUpperCase()}…`);
    try {
      const filters = {
        industry: filterIndustry !== 'All' ? filterIndustry : undefined,
        has_website: filterWebsite === 'All' ? undefined : filterWebsite === 'Yes',
        min_score: scoreMin > 0 ? scoreMin : undefined,
        limit: 500,
      };
      if (format === 'csv') await exportApi.downloadCsv(filters);
      else if (format === 'excel') await exportApi.downloadExcel(filters);
      else await exportApi.downloadPdf(filters, 'Business Intelligence Report');
      setExportStatus(null);
    } catch (err) {
      setExportStatus(`Export failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
      setTimeout(() => setExportStatus(null), 5000);
    }
  }, [filterIndustry, filterWebsite, scoreMin]);

  const { data: businessData, isLoading } = useQuery({
    queryKey: ['businesses', 'leads', filterIndustry, filterWebsite, scoreMin],
    queryFn: () => businessesApi.list({
      page: 1,
      page_size: 100,
      sort_by: 'opportunity_score',
      has_website: filterWebsite === 'All' ? undefined : filterWebsite === 'Yes',
      min_score: scoreMin > 0 ? scoreMin : undefined,
      industry: filterIndustry !== 'All' ? filterIndustry : undefined,
    }),
    staleTime: 30_000,
  });

  const allLeads = useMemo<LeadBusiness[]>(() => {
    if (!businessData?.items) return [];
    return businessData.items
      .sort((a, b) => (b.opportunity_score ?? 0) - (a.opportunity_score ?? 0))
      .map((b, i) => businessToLead(b, i + 1));
  }, [businessData]);

  const filtered = useMemo(() => {
    return allLeads.filter((lead) => {
      if (filterWebsite === 'Yes' && (!lead.hasWebsite || !lead.website)) return false;
      if (filterWebsite === 'No' && (lead.hasWebsite || Boolean(lead.website))) return false;
      if (searchQuery && !lead.name.toLowerCase().includes(searchQuery.toLowerCase()) && !lead.city.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      return true;
    }).sort((a, b) => b[sortBy] - a[sortBy]);
  }, [allLeads, searchQuery, sortBy, filterWebsite]);

  const top3 = useMemo(() => filtered.slice(0, 3), [filtered]);

  const toggleRow = useCallback((id: string) => {
    setExpandedRow((prev) => (prev === id ? null : id));
  }, []);

  return (
    <div className="min-h-full p-6 space-y-6">
      {/* Overlay when panel is open */}
      <AnimatePresence>
        {selectedLead && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
            onClick={() => setSelectedLead(null)}
          />
        )}
      </AnimatePresence>

      {/* Profile Panel */}
      {selectedLead && (
        <BusinessProfilePanel lead={selectedLead} onClose={() => setSelectedLead(null)} />
      )}

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.3), rgba(168,85,247,0.3))', border: '1px solid rgba(99,102,241,0.3)' }}
            >
              <Target size={20} className="text-indigo-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Lead Intelligence Center</h1>
              <p className="text-sm text-slate-400">Priority-ranked business opportunities</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {exportStatus && (
            <span className="text-xs text-amber-400 animate-pulse">{exportStatus}</span>
          )}
          <button
            onClick={() => handleExport('csv')}
            disabled={!!exportStatus}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-slate-300 hover:text-white transition-colors disabled:opacity-50"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
          >
            <FileSpreadsheet size={15} />
            CSV
          </button>
          <button
            onClick={() => handleExport('excel')}
            disabled={!!exportStatus}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-slate-300 hover:text-white transition-colors disabled:opacity-50"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
          >
            <FileText size={15} />
            Excel
          </button>
          <button
            onClick={() => handleExport('pdf')}
            disabled={!!exportStatus}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50"
            style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 4px 16px rgba(99,102,241,0.3)' }}
          >
            <Download size={15} />
            Export PDF
          </button>
        </div>
      </div>

      {/* ── Leaderboard ─────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Award size={16} className="text-amber-400" />
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Top Opportunities</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {top3.map((lead, i) => (
            <LeaderboardCard
              key={lead.id}
              lead={lead}
              position={(i + 1) as 1 | 2 | 3}
              onClick={() => setSelectedLead(lead)}
            />
          ))}
        </div>
      </div>

      {/* ── Filter & Sort Bar ────────────────────────────────────────────── */}
      <GlassCard padding="sm">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-0">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              placeholder="Search businesses..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-300 placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 transition-all"
            />
          </div>

          {/* Sort */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-indigo-500/50 cursor-pointer"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-slate-900">
                {o.label}
              </option>
            ))}
          </select>

          {/* Industry Filter */}
          <select
            value={filterIndustry}
            onChange={(e) => setFilterIndustry(e.target.value)}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-indigo-500/50 cursor-pointer"
          >
            {INDUSTRIES.map((i) => (
              <option key={i} value={i} className="bg-slate-900">{i}</option>
            ))}
          </select>

          {/* Website Filter */}
          <div className="flex rounded-lg overflow-hidden border border-white/10">
            {(['All', 'Yes', 'No'] as const).map((v) => (
              <button
                key={v}
                onClick={() => setFilterWebsite(v)}
                className={cn(
                  'px-3 py-2 text-xs font-medium transition-colors',
                  filterWebsite === v
                    ? 'bg-indigo-500/20 text-indigo-300'
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                )}
              >
                {v === 'All' ? 'Website: All' : v === 'Yes' ? 'Has Website' : 'No Website'}
              </button>
            ))}
          </div>

          {/* Results count */}
          <span className="text-xs text-slate-500 whitespace-nowrap flex-shrink-0">
            {filtered.length} results
          </span>
        </div>
      </GlassCard>

      {/* ── Leads Table ─────────────────────────────────────────────────── */}
      <GlassCard padding="none">
        <div className="overflow-x-auto">
          <div className="min-w-[950px]">
            {/* Table Header */}
            <div
              className="grid grid-cols-12 gap-2 px-6 py-3 border-b border-white/5"
          style={{ background: 'rgba(0,0,0,0.2)' }}
        >
          {['Rank', 'Business', 'Website', 'Scores', 'Opp. Score', 'Revenue', 'Opportunities', 'Actions'].map((h) => (
            <div
              key={h}
              className={cn(
                'text-xs font-semibold text-slate-500 uppercase tracking-wider',
                h === 'Business' ? 'col-span-3' : h === 'Scores' ? 'col-span-2' : h === 'Opportunities' ? 'col-span-2' : ''
              )}
            >
              {h}
            </div>
          ))}
        </div>

        {/* Table Rows */}
        <div className="divide-y divide-white/5">
          {filtered.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <Target size={32} className="text-slate-600 mx-auto mb-3" />
              <p className="text-slate-400">No leads match your filters</p>
            </div>
          ) : (
            filtered.map((lead) => (
              <React.Fragment key={lead.id}>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className={cn(
                    'grid grid-cols-12 gap-2 px-6 py-4 items-center cursor-pointer transition-colors',
                    expandedRow === lead.id ? 'bg-indigo-500/5' : 'hover:bg-white/3'
                  )}
                  onClick={() => toggleRow(lead.id)}
                >
                  {/* Rank */}
                  <div className="flex flex-col items-center gap-1">
                    <span className="text-base font-bold text-slate-300">#{lead.rank}</span>
                    <RankMovement value={lead.rankMovement} />
                  </div>

                  {/* Business */}
                  <div className="col-span-3 min-w-0">
                    <div className="font-semibold text-white text-sm truncate">{lead.name}</div>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <MapPin size={11} className="text-slate-500 flex-shrink-0" />
                      <span className="text-xs text-slate-400 truncate">{lead.city}</span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      <Badge variant="info" size="sm">{lead.industry}</Badge>
                      {lead.completenessScore > 0 && <CompletenessBadge score={lead.completenessScore} />}
                    </div>
                  </div>

                  {/* Website Status */}
                  <div>
                    {lead.hasWebsite ? (
                      <div className="flex items-center gap-1 text-emerald-400">
                        <CheckCircle2 size={14} />
                        <span className="text-xs">Active</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1 text-red-400">
                        <AlertCircle size={14} />
                        <span className="text-xs">None</span>
                      </div>
                    )}
                  </div>

                  {/* Scores */}
                  <div className="col-span-2 space-y-1">
                    <MiniScoreBar label="SEO" value={lead.seoScore} />
                    <MiniScoreBar label="Mob" value={lead.mobileScore} />
                    <MiniScoreBar label="UI" value={lead.uiScore} />
                  </div>

                  {/* Opportunity Score */}
                  <div className="flex justify-center">
                    <OpportunityBadge score={lead.opportunityScore} />
                  </div>

                  {/* Revenue */}
                  <div>
                    <div className="text-xs font-semibold text-white">
                      {formatCurrency(lead.revenuePotentialMin, { notation: 'compact' })}
                    </div>
                    <div className="text-xs text-slate-500">
                      – {formatCurrency(lead.revenuePotentialMax, { notation: 'compact' })}
                    </div>
                  </div>

                  {/* Opportunities */}
                  <div className="col-span-2 flex flex-wrap gap-1">
                    {lead.opportunities.map((opp) => (
                      <span
                        key={opp}
                        className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-400 border border-indigo-500/20"
                      >
                        {opp}
                      </span>
                    ))}
                  </div>

                  {/* Actions */}
                  <div
                    className="flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => setSelectedLead(lead)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                      title="View Profile"
                    >
                      <Eye size={14} />
                    </button>
                    <button
                      className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                      title="Add to CRM"
                    >
                      <Plus size={14} />
                    </button>
                    {lead.hasWebsite && (
                      <a
                        href={`https://${lead.website}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                      >
                        <ExternalLink size={14} />
                      </a>
                    )}
                    <button
                      onClick={() => toggleRow(lead.id)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors ml-1"
                    >
                      {expandedRow === lead.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                  </div>
                </motion.div>

                {/* Expanded Row */}
                <AnimatePresence>
                  {expandedRow === lead.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <ExpandedRow lead={lead} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </React.Fragment>
            ))
          )}
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
