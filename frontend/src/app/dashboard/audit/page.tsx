'use client';

import React, { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { auditsApi } from '@/lib/api';
import type { AuditReportRaw } from '@/lib/api';
import {
  Search,
  Plus,
  X,
  ScanSearch,
  Globe,
  Monitor,
  Smartphone,
  Zap,
  Layers,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  Info,
  ExternalLink,
  RefreshCw,
  Trash2,
  Eye,
  Building2,
  Check,
  Square,
  LayoutGrid,
  Filter,
  Clock,
  TrendingUp,
  TrendingDown,
  Code2,
  Bot,
  ImageOff,
  BarChart2,
} from 'lucide-react';
import GlassCard from '@/components/ui/GlassCard';
import Badge from '@/components/ui/Badge';
import ScoreRing from '@/components/ui/ScoreRing';
import ProgressBar from '@/components/ui/ProgressBar';
import StatCard from '@/components/ui/StatCard';

// ─── Types ────────────────────────────────────────────────────────────────────

type AuditStatus = 'completed' | 'running' | 'failed';
type ScoreCategory = 'ui' | 'ux' | 'seo' | 'mobile' | 'speed';
type IssueSeverity = 'critical' | 'warning' | 'info';

interface ScoreBreakdown {
  ui: number;
  ux: number;
  seo: number;
  mobile: number;
  speed: number;
}

interface AuditIssue {
  id: string;
  category: ScoreCategory | 'general';
  severity: IssueSeverity;
  title: string;
  description: string;
}

interface Recommendation {
  id: string;
  title: string;
  description: string;
  impact: 'high' | 'medium' | 'low';
}

interface AuditReport {
  id: string;
  businessName: string;
  url: string;
  status: AuditStatus;
  overallScore: number;
  scores: ScoreBreakdown;
  issues: AuditIssue[];
  recommendations: Recommendation[];
  techStack: string[];
  performanceMetrics: {
    lcp: string;
    fid: string;
    cls: string;
    ttfb: string;
    pageSize: string;
    requests: number;
  };
  aiAnalysis?: string | { executive_summary?: string; strengths?: string[]; weaknesses?: string[]; opportunities?: string[]; estimated_value?: string };
  industry: string;
  auditedAt: string;
}

// ─── Map backend audit to local AuditReport ───────────────────────────────────

function rawToAuditReport(a: AuditReportRaw): AuditReport {
  const pm = (a.performance_metrics ?? {}) as Record<string, unknown>;

  const mapSeverity = (s: unknown): IssueSeverity => {
    const sv = String(s ?? '').toLowerCase();
    if (sv === 'critical') return 'critical';
    if (sv === 'warning') return 'warning';
    return 'info';
  };

  const mapCat = (c: unknown): ScoreCategory | 'general' => {
    const cat = String(c ?? '').toLowerCase();
    if (cat === 'seo') return 'seo';
    if (cat === 'mobile') return 'mobile';
    if (cat === 'speed') return 'speed';
    if (cat === 'ui') return 'ui';
    if (cat === 'ux' || cat === 'accessibility') return 'ux';
    return 'general';
  };

  const allIssues = [
    ...(a.seo_issues ?? []).map((issue: unknown, i) => {
      const obj = issue as Record<string, unknown>;
      return {
        id: `seo-${i}`,
        category: mapCat(obj?.category ?? 'seo'),
        severity: mapSeverity(obj?.severity),
        title: String(obj?.title ?? 'SEO Issue'),
        description: String(obj?.description ?? ''),
      };
    }),
    ...(a.accessibility_issues ?? []).map((issue: unknown, i) => {
      const obj = issue as Record<string, unknown>;
      return {
        id: `acc-${i}`,
        category: mapCat(obj?.category ?? 'ux'),
        severity: mapSeverity(obj?.severity),
        title: String(obj?.title ?? 'Accessibility Issue'),
        description: String(obj?.description ?? ''),
      };
    }),
  ];

  // Assign impact based on severity
  const impactMap: Record<IssueSeverity, 'high' | 'medium' | 'low'> = {
    critical: 'high',
    warning: 'medium',
    info: 'low',
  };

  const ttfbMs = Number(pm.ttfb_ms ?? pm.ttfb ?? 0);
  const pageSizeKb = Number(pm.page_size_kb ?? 0);

  return {
    id: a.id,
    businessName: a.website_url ?? `Audit ${a.id.slice(0, 8)}`,
    url: a.website_url ?? '',
    status: (a.status as AuditStatus) ?? 'completed',
    overallScore: a.overall_score ?? 0,
    scores: {
      ui: a.ui_score ?? 0,
      ux: a.ux_score ?? 0,
      seo: a.seo_score ?? 0,
      mobile: a.mobile_score ?? 0,
      speed: a.speed_score ?? 0,
    },
    issues: allIssues,
    recommendations: (a.recommendations ?? []).map((r: unknown, i: number) => {
      const rec = typeof r === 'string' ? { title: r, description: '' } : (r as { title: string; description?: string });
      return {
        id: `rec-${i}`,
        title: rec.title ?? String(r),
        description: rec.description ?? '',
        impact: (i === 0 ? 'high' : i < 3 ? 'medium' : 'low') as 'high' | 'medium' | 'low',
      };
    }),
    techStack: (a.tech_stack ?? []).map((t: unknown) => typeof t === 'string' ? t : (t as { name: string }).name ?? '').filter(Boolean),
    performanceMetrics: {
      lcp: ttfbMs > 0 ? `${(ttfbMs / 1000).toFixed(2)}s` : '—',
      fid: '—',
      cls: '—',
      ttfb: ttfbMs > 0 ? `${ttfbMs}ms` : '—',
      pageSize: pageSizeKb > 0 ? `${pageSizeKb}KB` : '—',
      requests: Number(pm.render_blocking_scripts ?? 0),
    },
    aiAnalysis: a.ai_analysis ?? undefined,
    industry: '',
    auditedAt: a.completed_at ? a.completed_at.slice(0, 10) : '—',
  };
}

const STATUS_FILTERS = ['All', 'Completed', 'Running', 'Failed'];
const INDUSTRIES = ['All Industries', 'Retail', 'Healthcare', 'Home Services', 'Wellness', 'Technology'];

const SCORE_LABELS: Record<ScoreCategory, string> = {
  ui: 'UI Design',
  ux: 'User Experience',
  seo: 'SEO',
  mobile: 'Mobile',
  speed: 'Speed',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function statusBadge(status: AuditStatus) {
  switch (status) {
    case 'completed': return <Badge variant="success" dot>Completed</Badge>;
    case 'running':   return <Badge variant="info" dot>Running</Badge>;
    case 'failed':    return <Badge variant="danger" dot>Failed</Badge>;
  }
}

function severityBadge(severity: IssueSeverity) {
  switch (severity) {
    case 'critical': return <Badge variant="danger" size="sm">Critical</Badge>;
    case 'warning':  return <Badge variant="warning" size="sm">Warning</Badge>;
    case 'info':     return <Badge variant="info" size="sm">Info</Badge>;
  }
}

function impactBadge(impact: 'high' | 'medium' | 'low') {
  switch (impact) {
    case 'high':   return <Badge variant="danger" size="sm">High Impact</Badge>;
    case 'medium': return <Badge variant="warning" size="sm">Medium Impact</Badge>;
    case 'low':    return <Badge variant="slate" size="sm">Low Impact</Badge>;
  }
}

function severityIcon(severity: IssueSeverity) {
  switch (severity) {
    case 'critical': return <AlertCircle size={14} className="text-red-400 flex-shrink-0" />;
    case 'warning':  return <AlertTriangle size={14} className="text-amber-400 flex-shrink-0" />;
    case 'info':     return <Info size={14} className="text-sky-400 flex-shrink-0" />;
  }
}

function MetricBadge({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div
      className="flex flex-col items-center gap-1 rounded-xl p-3 min-w-[90px]"
      style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}
    >
      <span className="text-xs text-slate-500 font-medium">{label}</span>
      <span className={`text-sm font-bold ${good === undefined ? 'text-white' : good ? 'text-emerald-400' : 'text-red-400'}`}>
        {value}
      </span>
    </div>
  );
}

// ─── Audit Card ───────────────────────────────────────────────────────────────

function AuditCard({
  audit,
  selected,
  onSelect,
  onClick,
}: {
  audit: AuditReport;
  selected: boolean;
  onSelect: (id: string) => void;
  onClick: () => void;
}) {
  const isActive = audit.status === 'running';
  const isFailed = audit.status === 'failed';

  return (
    <motion.div
      whileHover={!isActive && !isFailed ? { y: -4, boxShadow: '0 24px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(99,102,241,0.25)' } : {}}
      transition={{ duration: 0.2 }}
      className="relative rounded-xl overflow-hidden group"
      style={{
        background: selected ? 'rgba(99,102,241,0.08)' : 'rgba(14,14,32,0.6)',
        backdropFilter: 'blur(16px)',
        border: selected ? '1px solid rgba(99,102,241,0.3)' : '1px solid rgba(255,255,255,0.07)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      }}
    >
      {/* Select checkbox (top-left) */}
      <button
        onClick={(e) => { e.stopPropagation(); onSelect(audit.id); }}
        className={`absolute top-3 left-3 z-10 w-5 h-5 rounded flex items-center justify-center transition-all ${
          selected
            ? 'bg-indigo-500 border-indigo-500'
            : 'bg-transparent border border-white/20 opacity-0 group-hover:opacity-100'
        }`}
        style={{ border: selected ? 'none' : undefined }}
      >
        {selected && <Check size={12} className="text-white" />}
      </button>

      {/* Screenshot area */}
      <div
        className="relative h-36 cursor-pointer overflow-hidden"
        onClick={onClick}
        style={{ background: 'linear-gradient(135deg, rgba(30,30,60,0.8), rgba(20,20,45,0.9))' }}
      >
        {/* Fake browser chrome */}
        <div className="flex items-center gap-1.5 px-3 py-2 border-b border-white/5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
          <div className="flex-1 mx-2 h-4 rounded bg-white/5 flex items-center px-2">
            <span className="text-xs text-slate-500 truncate">{audit.url}</span>
          </div>
        </div>

        {/* Screenshot placeholder */}
        <div className="flex items-center justify-center h-[calc(100%-2.25rem)]">
          {isActive ? (
            <div className="flex flex-col items-center gap-2">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
              >
                <ScanSearch size={28} className="text-indigo-400" />
              </motion.div>
              <span className="text-xs text-slate-400">Scanning…</span>
            </div>
          ) : isFailed ? (
            <div className="flex flex-col items-center gap-2">
              <AlertCircle size={28} className="text-red-400" />
              <span className="text-xs text-slate-500">Audit failed</span>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1 opacity-30">
              <ImageOff size={24} className="text-slate-400" />
              <span className="text-xs text-slate-500">Screenshot</span>
            </div>
          )}
        </div>

        {/* Hover overlay with action */}
        {!isActive && !isFailed && (
          <div
            className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ background: 'rgba(0,0,0,0.55)' }}
          >
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl font-semibold text-sm text-white" style={{ background: 'rgba(99,102,241,0.8)' }}>
              <Eye size={15} />
              View Report
            </div>
          </div>
        )}

        {/* Status badge overlay */}
        <div className="absolute top-8 right-2">
          {statusBadge(audit.status)}
        </div>
      </div>

      {/* Card body */}
      <div className="p-4 cursor-pointer" onClick={onClick}>
        {/* Business name + URL */}
        <div className="mb-3">
          <p className="font-semibold text-white text-sm leading-snug group-hover:text-indigo-300 transition-colors truncate">
            {audit.businessName}
          </p>
          <a
            href={`https://${audit.url}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-400 transition-colors mt-0.5"
          >
            <Globe size={10} />
            {audit.url}
            <ExternalLink size={9} />
          </a>
        </div>

        {/* Score rings row */}
        {!isActive && !isFailed ? (
          <>
            <div className="flex items-end justify-between mb-3">
              {(Object.keys(audit.scores) as ScoreCategory[]).map((cat) => (
                <ScoreRing
                  key={cat}
                  score={audit.scores[cat]}
                  size={38}
                  strokeWidth={3.5}
                  label={cat.toUpperCase()}
                  showValue
                  animate={false}
                />
              ))}
            </div>

            {/* Overall score */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">Overall Score</span>
              <div className="flex items-center gap-2">
                <div
                  className="px-3 py-1 rounded-full text-sm font-bold"
                  style={{
                    background: audit.overallScore >= 70 ? 'rgba(16,185,129,0.15)' : audit.overallScore >= 40 ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)',
                    color: audit.overallScore >= 70 ? '#34d399' : audit.overallScore >= 40 ? '#fbbf24' : '#f87171',
                    border: `1px solid ${audit.overallScore >= 70 ? 'rgba(16,185,129,0.2)' : audit.overallScore >= 40 ? 'rgba(245,158,11,0.2)' : 'rgba(239,68,68,0.2)'}`,
                  }}
                >
                  {audit.overallScore}
                </div>
              </div>
            </div>
          </>
        ) : null}

        {/* View Report button */}
        {!isActive && !isFailed && (
          <button
            onClick={onClick}
            className="mt-3 w-full py-2 rounded-lg text-xs font-semibold text-indigo-400 border border-indigo-500/20 hover:bg-indigo-500/10 transition-colors"
          >
            View Report
          </button>
        )}
      </div>
    </motion.div>
  );
}

// ─── Audit Detail Modal ───────────────────────────────────────────────────────

function AuditDetailModal({
  audit,
  onClose,
}: {
  audit: AuditReport;
  onClose: () => void;
}) {
  const [screenshotTab, setScreenshotTab] = useState<'desktop' | 'mobile'>('desktop');
  const [openRecommendation, setOpenRecommendation] = useState<string | null>(null);
  const [issueCategory, setIssueCategory] = useState<string>('All');

  const issueCategories = ['All', ...Array.from(new Set(audit.issues.map((i) => i.category)))];
  const filteredIssues = audit.issues.filter(
    (i) => issueCategory === 'All' || i.category === issueCategory
  );

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-start justify-center p-4 overflow-y-auto"
        style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(12px)' }}
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 24, scale: 0.97 }}
          transition={{ duration: 0.25 }}
          className="relative w-full max-w-5xl my-6 rounded-2xl overflow-hidden"
          style={{
            background: 'rgba(12,12,28,0.98)',
            backdropFilter: 'blur(24px)',
            border: '1px solid rgba(255,255,255,0.1)',
            boxShadow: '0 40px 80px rgba(0,0,0,0.7)',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Modal header */}
          <div
            className="flex items-center justify-between px-6 py-4 border-b sticky top-0 z-10"
            style={{ background: 'rgba(12,12,28,0.95)', borderColor: 'rgba(255,255,255,0.08)', backdropFilter: 'blur(16px)' }}
          >
            <div>
              <h2 className="text-lg font-bold text-white">{audit.businessName}</h2>
              <div className="flex items-center gap-3 mt-0.5">
                <a
                  href={`https://${audit.url}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  <Globe size={11} />
                  {audit.url}
                  <ExternalLink size={9} />
                </a>
                {statusBadge(audit.status)}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <ScoreRing score={audit.overallScore} size={52} strokeWidth={5} label="Overall" />
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          {/* Two-column layout */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 divide-y lg:divide-y-0 lg:divide-x divide-white/8">
            {/* ── Left: Screenshots ── */}
            <div className="p-6 space-y-4">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Monitor size={15} className="text-indigo-400" />
                Screenshots
              </h3>

              {/* Screenshot tabs */}
              <div
                className="flex rounded-lg overflow-hidden border border-white/10 self-start"
                style={{ background: 'rgba(255,255,255,0.04)' }}
              >
                {(['desktop', 'mobile'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setScreenshotTab(tab)}
                    className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors capitalize ${
                      screenshotTab === tab
                        ? 'bg-indigo-500/25 text-white'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {tab === 'desktop' ? <Monitor size={13} /> : <Smartphone size={13} />}
                    {tab}
                  </button>
                ))}
              </div>

              {/* Screenshot placeholder */}
              <div
                className="rounded-xl overflow-hidden"
                style={{ background: 'rgba(20,20,50,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}
              >
                {/* Browser chrome */}
                <div className="flex items-center gap-1.5 px-3 py-2 border-b border-white/5">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-500/60" />
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
                  <div className="flex-1 mx-2 h-4 rounded bg-white/5 flex items-center px-2">
                    <span className="text-xs text-slate-500">{audit.url}</span>
                  </div>
                </div>
                <div
                  className={`flex items-center justify-center ${screenshotTab === 'desktop' ? 'h-52' : 'h-72 max-w-[200px] mx-auto'}`}
                >
                  <div className="flex flex-col items-center gap-2 opacity-30">
                    <ImageOff size={32} className="text-slate-400" />
                    <span className="text-xs text-slate-500">{screenshotTab === 'desktop' ? 'Desktop' : 'Mobile'} screenshot</span>
                  </div>
                </div>
              </div>

              {/* Performance metrics table */}
              <div>
                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <BarChart2 size={13} />
                  Performance Metrics
                </h4>
                <div className="grid grid-cols-3 gap-2">
                  <MetricBadge
                    label="TTFB"
                    value={audit.performanceMetrics.ttfb}
                    good={audit.performanceMetrics.ttfb !== '—' && parseInt(audit.performanceMetrics.ttfb) < 500}
                  />
                  <MetricBadge
                    label="Response Time"
                    value={audit.performanceMetrics.lcp}
                    good={audit.performanceMetrics.lcp !== '—' && parseFloat(audit.performanceMetrics.lcp) < 1.5}
                  />
                  <MetricBadge label="Page Size" value={audit.performanceMetrics.pageSize} />
                  <MetricBadge
                    label="Blocking JS"
                    value={audit.performanceMetrics.requests > 0 ? `${audit.performanceMetrics.requests} files` : '0 files'}
                    good={audit.performanceMetrics.requests === 0}
                  />
                </div>
              </div>

              {/* Tech stack */}
              {audit.techStack.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                    <Code2 size={13} />
                    Tech Stack
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {audit.techStack.map((tech) => (
                      <span
                        key={tech}
                        className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: 'rgba(99,102,241,0.12)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.2)' }}
                      >
                        {tech}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* ── Right: Scores + Issues + Recs + AI ── */}
            <div className="p-6 space-y-6 overflow-y-auto max-h-[80vh]">
              {/* Score breakdown */}
              <div>
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <TrendingUp size={15} className="text-purple-400" />
                  Score Breakdown
                </h3>
                <div className="space-y-3">
                  {(Object.keys(audit.scores) as ScoreCategory[]).map((cat) => (
                    <div key={cat}>
                      <ProgressBar
                        value={audit.scores[cat]}
                        label={SCORE_LABELS[cat]}
                        showValue
                        color="auto"
                        size="md"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* Issues list */}
              {audit.issues.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                      <AlertCircle size={15} className="text-red-400" />
                      Issues
                      <span className="px-1.5 py-0.5 rounded-full text-xs" style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>
                        {audit.issues.length}
                      </span>
                    </h3>
                  </div>

                  {/* Category filter */}
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {issueCategories.map((cat) => (
                      <button
                        key={cat}
                        onClick={() => setIssueCategory(cat)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors capitalize ${
                          issueCategory === cat
                            ? 'bg-indigo-500/25 text-white'
                            : 'text-slate-400 hover:text-white bg-white/4 hover:bg-white/8'
                        }`}
                      >
                        {cat}
                      </button>
                    ))}
                  </div>

                  <div className="space-y-2">
                    {filteredIssues.map((issue) => (
                      <div
                        key={issue.id}
                        className="rounded-xl p-3.5"
                        style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
                      >
                        <div className="flex items-start gap-2.5">
                          {severityIcon(issue.severity)}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-sm font-medium text-white">{issue.title}</span>
                              {severityBadge(issue.severity)}
                            </div>
                            <p className="text-xs text-slate-400 mt-1 leading-relaxed">{issue.description}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations accordion */}
              {audit.recommendations.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <CheckCircle size={15} className="text-emerald-400" />
                    Recommendations
                  </h3>
                  <div className="space-y-2">
                    {audit.recommendations.map((rec) => (
                      <div
                        key={rec.id}
                        className="rounded-xl overflow-hidden"
                        style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
                      >
                        <button
                          onClick={() => setOpenRecommendation(openRecommendation === rec.id ? null : rec.id)}
                          className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-sm font-medium text-white truncate">{rec.title}</span>
                            {impactBadge(rec.impact)}
                          </div>
                          <ChevronDown
                            size={15}
                            className={`text-slate-400 flex-shrink-0 transition-transform ${openRecommendation === rec.id ? 'rotate-180' : ''}`}
                          />
                        </button>
                        <AnimatePresence>
                          {openRecommendation === rec.id && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: 'auto', opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              transition={{ duration: 0.2 }}
                              className="overflow-hidden"
                            >
                              <div className="px-4 pb-4 text-sm text-slate-400 leading-relaxed border-t border-white/5 pt-3">
                                {rec.description}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Analysis */}
              {audit.aiAnalysis && (
                <div
                  className="rounded-xl p-4"
                  style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)' }}
                >
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Bot size={15} className="text-indigo-400" />
                    Audit Summary
                  </h3>
                  {typeof audit.aiAnalysis === 'string' ? (
                    <div className="text-sm text-slate-300 leading-relaxed space-y-2">
                      {audit.aiAnalysis.split('\n').map((line, i) => {
                        if (line.startsWith('**') && line.endsWith('**')) {
                          return <p key={i} className="font-semibold text-white mt-3 first:mt-0">{line.replace(/\*\*/g, '')}</p>;
                        }
                        if (line.startsWith('- ')) {
                          return <p key={i} className="pl-3 border-l-2 border-indigo-500/30 text-slate-400">{line.slice(2)}</p>;
                        }
                        if (line.trim() === '') return null;
                        return <p key={i}>{line}</p>;
                      })}
                    </div>
                  ) : (
                    <div className="space-y-3 text-sm">
                      {audit.aiAnalysis.executive_summary && (
                        <p className="text-slate-300 leading-relaxed">{audit.aiAnalysis.executive_summary}</p>
                      )}
                      {audit.aiAnalysis.strengths && audit.aiAnalysis.strengths.length > 0 && (
                        <div>
                          <p className="text-emerald-400 font-semibold mb-1">Strengths</p>
                          {audit.aiAnalysis.strengths.map((s, i) => <p key={i} className="pl-3 border-l-2 border-emerald-500/30 text-slate-400">{s}</p>)}
                        </div>
                      )}
                      {audit.aiAnalysis.weaknesses && audit.aiAnalysis.weaknesses.length > 0 && (
                        <div>
                          <p className="text-red-400 font-semibold mb-1">Weaknesses</p>
                          {audit.aiAnalysis.weaknesses.map((s, i) => <p key={i} className="pl-3 border-l-2 border-red-500/30 text-slate-400">{s}</p>)}
                        </div>
                      )}
                      {audit.aiAnalysis.opportunities && audit.aiAnalysis.opportunities.length > 0 && (
                        <div>
                          <p className="text-indigo-400 font-semibold mb-1">Opportunities</p>
                          {audit.aiAnalysis.opportunities.map((s, i) => <p key={i} className="pl-3 border-l-2 border-indigo-500/30 text-slate-400">{s}</p>)}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// ─── Bulk Audit Progress Modal ────────────────────────────────────────────────

function BulkAuditModal({
  count,
  onClose,
}: {
  count: number;
  onClose: () => void;
}) {
  const [progress, setProgress] = React.useState(0);

  React.useEffect(() => {
    if (progress >= 100) return;
    const t = setInterval(() => setProgress((p) => Math.min(100, p + Math.random() * 12 + 4)), 400);
    return () => clearInterval(t);
  }, [progress]);

  const done = Math.floor((progress / 100) * count);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(8px)' }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.92 }}
          className="w-full max-w-md rounded-2xl p-6"
          style={{
            background: 'rgba(14,14,32,0.98)',
            border: '1px solid rgba(255,255,255,0.1)',
            boxShadow: '0 40px 80px rgba(0,0,0,0.7)',
          }}
        >
          <div className="flex items-center gap-3 mb-5">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/15 flex items-center justify-center">
              <motion.div animate={{ rotate: 360 }} transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}>
                <ScanSearch size={18} className="text-indigo-400" />
              </motion.div>
            </div>
            <div>
              <h3 className="font-semibold text-white">Running Bulk Audit</h3>
              <p className="text-xs text-slate-400">{done} of {count} businesses audited</p>
            </div>
          </div>

          <ProgressBar value={progress} color="indigo" size="lg" showValue />

          <div className="mt-4 space-y-2 max-h-40 overflow-y-auto">
            {Array.from({ length: Math.min(done, count) }, (_, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-slate-400">
                <CheckCircle size={12} className="text-emerald-400 flex-shrink-0" />
                Auditing business {i + 1}…
              </div>
            ))}
          </div>

          {progress >= 100 ? (
            <button
              onClick={onClose}
              className="mt-5 w-full py-2.5 rounded-xl font-semibold text-sm text-white"
              style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)' }}
            >
              View Results
            </button>
          ) : (
            <button
              onClick={onClose}
              className="mt-5 w-full py-2.5 rounded-xl text-sm text-slate-400 hover:text-white border border-white/10 hover:bg-white/5 transition-colors"
            >
              Cancel
            </button>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// ─── New Audit Modal ──────────────────────────────────────────────────────────

function NewAuditModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState('');

  const mutation = useMutation({
    mutationFn: (websiteUrl: string) => auditsApi.create(websiteUrl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['audits'] });
      onClose();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    mutation.mutate(url.trim());
  };

  const inputClass =
    'w-full px-3 py-2 rounded-lg border border-white/10 bg-white/5 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-colors';

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
          className="w-full max-w-md rounded-2xl overflow-hidden"
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
              <h2 className="text-lg font-bold text-white">New Audit</h2>
              <p className="text-xs text-slate-400 mt-0.5">Run a website audit to get a full report</p>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          {/* Body */}
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            {/* URL */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">
                Website URL <span className="text-red-400">*</span>
              </label>
              <input
                type="url"
                placeholder="https://example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
                className={inputClass}
              />
            </div>

            {/* Business association note */}
            <div
              className="rounded-xl p-3.5 flex items-start gap-2.5"
              style={{ background: 'rgba(99,102,241,0.07)', border: '1px solid rgba(99,102,241,0.15)' }}
            >
              <Info size={14} className="text-indigo-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-slate-400 leading-relaxed">
                The audit will be automatically associated with a business if a matching record is found in the database.
              </p>
            </div>

            {/* Error */}
            {mutation.isError && (
              <p className="text-xs text-red-400">
                {(mutation.error as Error)?.message ?? 'Failed to create audit. Please try again.'}
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
              onClick={handleSubmit}
              disabled={mutation.isPending || !url.trim()}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl font-semibold text-sm text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 4px 20px rgba(99,102,241,0.4)' }}
            >
              {mutation.isPending ? (
                <>
                  <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
                    <RefreshCw size={15} />
                  </motion.div>
                  Starting…
                </>
              ) : (
                <>
                  <ScanSearch size={15} />
                  Run Audit
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

export default function AuditCenterPage() {
  const [showNewAudit, setShowNewAudit] = useState(false);
  const [statusFilter, setStatusFilter] = useState('All');
  const [scoreRange, setScoreRange] = useState<[number, number]>([0, 100]);
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [openAudit, setOpenAudit] = useState<AuditReport | null>(null);
  const [bulkRunning, setBulkRunning] = useState(false);

  const { data: auditData } = useQuery({
    queryKey: ['audits', 'list', statusFilter],
    queryFn: () => auditsApi.list({
      status: statusFilter !== 'All' ? statusFilter.toLowerCase() : undefined,
      min_score: scoreRange[0] > 0 ? scoreRange[0] : undefined,
      max_score: scoreRange[1] < 100 ? scoreRange[1] : undefined,
      page: 1,
      page_size: 50,
    }),
    staleTime: 5_000,
    refetchInterval: (query) => {
      const items = (query.state.data as { items?: { status: string }[] } | undefined)?.items ?? [];
      const hasRunning = items.some((a) => a.status === 'running' || a.status === 'pending');
      return hasRunning ? 3_000 : 15_000;
    },
  });

  const { data: statsData } = useQuery({
    queryKey: ['audits', 'stats'],
    queryFn: () => auditsApi.stats(),
    staleTime: 5_000,
    refetchInterval: 10_000,
  });

  const allAudits = useMemo<AuditReport[]>(() => {
    return (auditData?.items ?? []).map(rawToAuditReport);
  }, [auditData]);

  const filteredAudits = useMemo(() => {
    return allAudits.filter((a) => {
      if (search && !a.businessName.toLowerCase().includes(search.toLowerCase()) && !a.url.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [allAudits, search]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAll = () => {
    setSelectedIds(new Set(filteredAudits.map((a) => a.id)));
  };

  const clearSelection = () => setSelectedIds(new Set());

  const stats = useMemo(() => ({
    total: statsData?.total ?? 0,
    completed: statsData?.by_status?.completed ?? 0,
    avgScore: statsData?.avg_scores?.overall_score != null ? Math.round(statsData.avg_scores.overall_score) : 0,
    critical: 0,
  }), [statsData]);

  return (
    <div className="p-6 space-y-6 min-h-full">
      {/* ── Header ── */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Audit Center</h1>
          <p className="text-sm text-slate-400 mt-1">Website audit reports and performance insights</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Global search */}
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            <input
              type="text"
              placeholder="Search audits..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-4 py-2 rounded-lg border border-white/10 bg-white/5 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-colors w-52"
            />
          </div>
          <button
            onClick={() => setShowNewAudit(true)}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm text-white transition-all hover:opacity-90 active:scale-95"
            style={{ background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)', boxShadow: '0 4px 20px rgba(99,102,241,0.4)' }}
          >
            <Plus size={16} />
            New Audit
          </button>
        </div>
      </div>

      {/* ── Stats ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Audits" value={stats.total} icon={<ScanSearch size={18} />} iconColor="text-indigo-400" change={6} />
        <StatCard label="Completed" value={stats.completed} icon={<CheckCircle size={18} />} iconColor="text-emerald-400" change={10} />
        <StatCard label="Avg. Score" value={stats.avgScore} icon={<TrendingUp size={18} />} iconColor="text-purple-400" suffix="/100" />
        <StatCard label="Critical Issues" value={stats.critical} icon={<AlertCircle size={18} />} iconColor="text-red-400" change={-3} />
      </div>

      {/* ── Filter Bar ── */}
      <GlassCard padding="sm">
        <div className="flex items-center gap-3 flex-wrap px-2 py-1">
          {/* Status filter pills */}
          <div
            className="flex items-center rounded-lg overflow-hidden border border-white/10"
            style={{ background: 'rgba(255,255,255,0.04)' }}
          >
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-3 py-2 text-xs font-medium transition-colors ${statusFilter === s ? 'bg-indigo-500/25 text-white' : 'text-slate-400 hover:text-white'}`}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Score range */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 whitespace-nowrap">Score:</span>
            <input
              type="range"
              min={0}
              max={100}
              value={scoreRange[0]}
              onChange={(e) => setScoreRange([+e.target.value, scoreRange[1]])}
              className="w-20 accent-indigo-500 cursor-pointer"
            />
            <span className="text-xs text-slate-400 w-6 text-center">{scoreRange[0]}</span>
            <span className="text-xs text-slate-600">–</span>
            <input
              type="range"
              min={0}
              max={100}
              value={scoreRange[1]}
              onChange={(e) => setScoreRange([scoreRange[0], +e.target.value])}
              className="w-20 accent-indigo-500 cursor-pointer"
            />
            <span className="text-xs text-slate-400 w-6 text-center">{scoreRange[1]}</span>
          </div>

          {/* Results count */}
          <span className="text-xs text-slate-500 ml-auto">
            {filteredAudits.length} audit{filteredAudits.length !== 1 ? 's' : ''}
          </span>
        </div>
      </GlassCard>

      {/* ── Bulk Audit Section ── */}
      <AnimatePresence>
        {selectedIds.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="flex items-center gap-4 px-5 py-3.5 rounded-xl"
            style={{
              background: 'rgba(99,102,241,0.1)',
              border: '1px solid rgba(99,102,241,0.25)',
            }}
          >
            <span className="text-sm font-medium text-indigo-300">
              {selectedIds.size} selected
            </span>
            <button
              onClick={() => setBulkRunning(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white"
              style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 4px 16px rgba(99,102,241,0.4)' }}
            >
              <ScanSearch size={14} />
              Audit Selected ({selectedIds.size})
            </button>
            <button
              onClick={selectAll}
              className="text-xs text-slate-400 hover:text-white transition-colors"
            >
              Select all {filteredAudits.length}
            </button>
            <button
              onClick={clearSelection}
              className="ml-auto flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors"
            >
              <X size={13} />
              Clear
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Audit Cards Grid ── */}
      {filteredAudits.length === 0 ? (
        <GlassCard>
          <div className="py-16 flex flex-col items-center gap-3 text-center">
            <div className="w-14 h-14 rounded-2xl bg-indigo-500/10 flex items-center justify-center">
              <ScanSearch size={24} className="text-indigo-400" />
            </div>
            <p className="text-slate-300 font-medium">No audits match your filters</p>
            <p className="text-slate-500 text-sm">Adjust the filters above or run a new audit.</p>
            <button
              onClick={() => setShowNewAudit(true)}
              className="mt-2 flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white"
              style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)' }}
            >
              <Plus size={15} />
              Run New Audit
            </button>
          </div>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredAudits.map((audit, idx) => (
            <motion.div
              key={audit.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
            >
              <AuditCard
                audit={audit}
                selected={selectedIds.has(audit.id)}
                onSelect={toggleSelect}
                onClick={() => setOpenAudit(audit)}
              />
            </motion.div>
          ))}
        </div>
      )}

      {/* ── New Audit Modal ── */}
      {showNewAudit && <NewAuditModal onClose={() => setShowNewAudit(false)} />}

      {/* ── Audit Detail Modal ── */}
      {openAudit && (
        <AuditDetailModal audit={openAudit} onClose={() => setOpenAudit(null)} />
      )}

      {/* ── Bulk Audit Progress Modal ── */}
      {bulkRunning && (
        <BulkAuditModal count={selectedIds.size} onClose={() => { setBulkRunning(false); clearSelection(); }} />
      )}
    </div>
  );
}
