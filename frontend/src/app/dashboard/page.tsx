'use client';

import React, { useState, useMemo, useEffect } from 'react';

function ClientTime() {
  const [time, setTime] = useState('');
  useEffect(() => {
    setTime(new Date().toLocaleTimeString());
    const id = setInterval(() => setTime(new Date().toLocaleTimeString()), 60_000);
    return () => clearInterval(id);
  }, []);
  return <>{time}</>;
}
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
} from 'recharts';
import {
  Building2,
  Globe,
  AlertTriangle,
  DollarSign,
  TrendingUp,
  TrendingDown,
  Minus,
  MapPin,
  RefreshCw,
  BarChart3,
  Activity,
} from 'lucide-react';
import CountUp from 'react-countup';
import { analyticsApi, businessesApi, auditsApi } from '@/lib/api';
import type { AnalyticsDashboardRaw, IndustryBreakdownRaw, GeographyItemRaw, TrendRaw, ScoresDistributionRaw, BusinessRaw, AuditReportRaw } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';
import ProgressBar from '@/components/ui/ProgressBar';
import DashboardLayout from '@/components/layouts/DashboardLayout';

// ─── constants ────────────────────────────────────────────────────────────────

const INDUSTRY_COLORS = [
  '#6366f1', '#8b5cf6', '#a78bfa', '#c084fc',
  '#10b981', '#f59e0b', '#ef4444', '#3b82f6',
];

const SCORE_RANGES = [
  { range: '0–20', min: 0, max: 20, color: '#ef4444' },
  { range: '21–40', min: 21, max: 40, color: '#f59e0b' },
  { range: '41–60', min: 41, max: 60, color: '#eab308' },
  { range: '61–80', min: 61, max: 80, color: '#6366f1' },
  { range: '81–100', min: 81, max: 100, color: '#10b981' },
];

type TimePeriod = '7d' | '30d' | '90d';

// ─── skeleton components ──────────────────────────────────────────────────────

function StatSkeleton() {
  return (
    <div className="rounded-xl p-5 h-32 skeleton" />
  );
}

function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div className="skeleton rounded-xl w-full" style={{ height }} />
  );
}

// ─── custom tooltip ───────────────────────────────────────────────────────────

function CustomBarTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-xl px-4 py-3 text-sm shadow-2xl"
      style={{
        background: 'rgba(18,18,40,0.97)',
        border: '1px solid rgba(99,102,241,0.3)',
        backdropFilter: 'blur(16px)',
      }}
    >
      <p className="text-slate-400 mb-1">{label}</p>
      <p className="text-white font-semibold">{payload[0].value.toLocaleString()} businesses</p>
    </div>
  );
}

function CustomPieTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as IndustryBreakdownRaw;
  return (
    <div
      className="rounded-xl px-4 py-3 text-sm shadow-2xl"
      style={{
        background: 'rgba(18,18,40,0.97)',
        border: '1px solid rgba(99,102,241,0.3)',
        backdropFilter: 'blur(16px)',
      }}
    >
      <p className="text-white font-semibold mb-1">{d.industry}</p>
      <p className="text-slate-400">{d.count.toLocaleString()} businesses</p>
      {d.avg_score != null && <p className="text-indigo-400">Avg score: {d.avg_score}</p>}
    </div>
  );
}

function CustomAreaTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-xl px-4 py-3 text-sm shadow-2xl"
      style={{
        background: 'rgba(18,18,40,0.97)',
        border: '1px solid rgba(99,102,241,0.3)',
        backdropFilter: 'blur(16px)',
      }}
    >
      <p className="text-slate-400 mb-2 text-xs">{label}</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2 mb-0.5">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color }} />
          <span className="text-slate-300 capitalize">{p.dataKey}:</span>
          <span className="text-white font-medium">{p.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

// ─── stagger container ────────────────────────────────────────────────────────

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } },
};

// ─── sub-components ───────────────────────────────────────────────────────────

interface ScoreDistChartProps {
  data: ScoresDistributionRaw['histogram'];
  loading: boolean;
}

function ScoreDistChart({ data, loading }: ScoreDistChartProps) {
  const chartData = useMemo(() => {
    if (!data?.length) return [];
    return data.map((bucket, i) => ({
      range: bucket.label,
      count: bucket.count,
      fill: SCORE_RANGES[Math.min(i, SCORE_RANGES.length - 1)]?.color ?? '#6366f1',
    }));
  }, [data]);

  return (
    <GlassCard padding="none" className="h-full">
      <div className="p-5 pb-2">
        <div className="flex items-center gap-2 mb-1">
          <BarChart3 size={16} className="text-indigo-400" />
          <h3 className="text-sm font-semibold text-white">Opportunity Score Distribution</h3>
        </div>
        <p className="text-xs text-slate-500">Businesses grouped by opportunity score range</p>
      </div>
      <div className="px-2 pb-4">
        {loading ? (
          <ChartSkeleton height={240} />
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="barGrad0" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ef4444" stopOpacity={1} />
                  <stop offset="100%" stopColor="#ef444488" stopOpacity={0.7} />
                </linearGradient>
                <linearGradient id="barGrad1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f59e0b" stopOpacity={1} />
                  <stop offset="100%" stopColor="#f59e0b88" stopOpacity={0.7} />
                </linearGradient>
                <linearGradient id="barGrad2" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#eab308" stopOpacity={1} />
                  <stop offset="100%" stopColor="#eab30888" stopOpacity={0.7} />
                </linearGradient>
                <linearGradient id="barGrad3" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#818cf8" stopOpacity={1} />
                  <stop offset="100%" stopColor="#6366f188" stopOpacity={0.7} />
                </linearGradient>
                <linearGradient id="barGrad4" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={1} />
                  <stop offset="100%" stopColor="#10b98188" stopOpacity={0.7} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis
                dataKey="range"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}
              />
              <Tooltip content={<CustomBarTooltip />} cursor={{ fill: 'rgba(99,102,241,0.06)' }} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={52}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={`url(#barGrad${i})`} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </GlassCard>
  );
}

interface IndustryPieChartProps {
  data: IndustryBreakdownRaw[];
  loading: boolean;
}

function IndustryPieChart({ data, loading }: IndustryPieChartProps) {
  const top8 = useMemo(() => (data ?? []).slice(0, 8), [data]);
  const total = useMemo(() => top8.reduce((s, d) => s + d.count, 0), [top8]);

  const renderLegend = () => (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 mt-3 px-1">
      {top8.map((d, i) => (
        <div key={d.industry} className="flex items-center gap-2 min-w-0">
          <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: INDUSTRY_COLORS[i] }} />
          <span className="text-xs text-slate-400 truncate">{d.industry}</span>
          <span className="text-xs text-slate-500 ml-auto flex-shrink-0">{total > 0 ? Math.round(d.count / total * 100) : 0}%</span>
        </div>
      ))}
    </div>
  );

  return (
    <GlassCard padding="none" className="h-full">
      <div className="p-5 pb-2">
        <div className="flex items-center gap-2 mb-1">
          <Activity size={16} className="text-purple-400" />
          <h3 className="text-sm font-semibold text-white">Industries by Opportunity</h3>
        </div>
        <p className="text-xs text-slate-500">Top 8 categories by business count</p>
      </div>
      <div className="px-4 pb-4">
        {loading ? (
          <ChartSkeleton height={240} />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <defs>
                  {INDUSTRY_COLORS.map((c, i) => (
                    <radialGradient key={i} id={`pieGrad${i}`} cx="50%" cy="50%" r="50%">
                      <stop offset="0%" stopColor={c} stopOpacity={0.9} />
                      <stop offset="100%" stopColor={c} stopOpacity={0.6} />
                    </radialGradient>
                  ))}
                </defs>
                <Pie
                  data={top8}
                  cx="50%"
                  cy="50%"
                  innerRadius={52}
                  outerRadius={88}
                  paddingAngle={3}
                  dataKey="count"
                  animationBegin={200}
                  animationDuration={900}
                >
                  {top8.map((_, i) => (
                    <Cell key={i} fill={`url(#pieGrad${i})`} stroke="transparent" />
                  ))}
                </Pie>
                <Tooltip content={<CustomPieTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            {renderLegend()}
          </>
        )}
      </div>
    </GlassCard>
  );
}

// Normalize trend data: merge businesses_discovered and audits_completed into a unified series
function normalizeTrendData(trend: TrendRaw | undefined): Array<{ date: string; businesses: number; audits: number }> {
  if (!trend) return [];
  const map = new Map<string, { businesses: number; audits: number }>();
  for (const pt of trend.businesses_discovered) {
    map.set(pt.date, { businesses: pt.count, audits: 0 });
  }
  for (const pt of trend.audits_completed) {
    const existing = map.get(pt.date);
    if (existing) existing.audits = pt.count;
    else map.set(pt.date, { businesses: 0, audits: pt.count });
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, v]) => ({ date, ...v }));
}

interface RevenueTrendChartProps {
  trend: TrendRaw | undefined;
  loading: boolean;
  period: TimePeriod;
  onPeriodChange: (p: TimePeriod) => void;
}

function RevenueTrendChart({ trend, loading, period, onPeriodChange }: RevenueTrendChartProps) {
  const data = useMemo(() => normalizeTrendData(trend), [trend]);
  const sliced = useMemo(() => {
    if (!data.length) return [];
    const days = period === '7d' ? 7 : period === '30d' ? 30 : 90;
    return data.slice(-days);
  }, [data, period]);

  const periods: TimePeriod[] = ['7d', '30d', '90d'];

  return (
    <GlassCard padding="none">
      <div className="flex items-center justify-between px-5 pt-5 pb-2">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp size={16} className="text-emerald-400" />
            <h3 className="text-sm font-semibold text-white">Revenue Potential by Industry</h3>
          </div>
          <p className="text-xs text-slate-500">Discovery & audit activity driving revenue pipeline</p>
        </div>
        <div className="flex items-center gap-1 rounded-lg p-1" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}>
          {periods.map((p) => (
            <button
              key={p}
              onClick={() => onPeriodChange(p)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                period === p
                  ? 'bg-indigo-500/30 text-indigo-300 shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="px-2 pb-4">
        {loading ? (
          <ChartSkeleton height={220} />
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={sliced} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="areaGrad1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="areaGrad2" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="areaGrad3" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#a78bfa" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => {
                  const d = new Date(v);
                  return `${d.getMonth() + 1}/${d.getDate()}`;
                }}
                interval={period === '7d' ? 0 : period === '30d' ? 4 : 12}
              />
              <YAxis
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}
              />
              <Tooltip content={<CustomAreaTooltip />} />
              <Area type="monotone" dataKey="businesses" stroke="#6366f1" strokeWidth={2} fill="url(#areaGrad1)" dot={false} />
              <Area type="monotone" dataKey="audits" stroke="#10b981" strokeWidth={2} fill="url(#areaGrad2)" dot={false} />
              <Area type="monotone" dataKey="discoveredBusinesses" stroke="#a78bfa" strokeWidth={2} fill="url(#areaGrad3)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="flex items-center gap-6 px-5 pb-4">
        {[
          { color: '#6366f1', label: 'Total Businesses' },
          { color: '#10b981', label: 'Audits' },
          { color: '#a78bfa', label: 'Discovered' },
        ].map((l) => (
          <div key={l.label} className="flex items-center gap-2">
            <span className="w-3 h-0.5 rounded-full" style={{ background: l.color }} />
            <span className="text-xs text-slate-500">{l.label}</span>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}

interface GeoTableProps {
  data: GeographyItemRaw[];
  loading: boolean;
}

function GeoTable({ data, loading }: GeoTableProps) {
  const maxCount = useMemo(() => Math.max(...(data ?? []).map((d) => d.count), 1), [data]);

  return (
    <GlassCard padding="none">
      <div className="flex items-center gap-2 px-5 pt-5 pb-3">
        <MapPin size={16} className="text-blue-400" />
        <h3 className="text-sm font-semibold text-white">Geographic Distribution</h3>
        <span className="ml-auto text-xs text-slate-500">Top 10 markets</span>
      </div>

      {loading ? (
        <div className="px-5 pb-5 space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 skeleton rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                {['Location', 'Businesses', 'Avg Score', 'Revenue Potential', 'Share'].map((h) => (
                  <th key={h} className="text-left text-xs font-medium text-slate-500 px-5 py-2.5">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data ?? []).slice(0, 10).map((row, i) => {
                const avgScore = row.avg_score ?? 0;
                const sharePct = Math.round((row.count / maxCount) * 100);
                return (
                  <motion.tr
                    key={row.location}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="group"
                    style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                  >
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <span
                          className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                          style={{ background: 'rgba(99,102,241,0.15)', color: '#818cf8' }}
                        >
                          {i + 1}
                        </span>
                        <p className="text-slate-200 font-medium">{row.location}</p>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-slate-200 font-medium">{row.count.toLocaleString()}</span>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-semibold ${
                            avgScore >= 70 ? 'text-emerald-400' :
                            avgScore >= 50 ? 'text-yellow-400' : 'text-red-400'
                          }`}
                        >
                          {avgScore}
                        </span>
                        <div className="w-16 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${avgScore}%`,
                              background: avgScore >= 70
                                ? 'linear-gradient(90deg,#10b981,#34d399)'
                                : avgScore >= 50
                                ? 'linear-gradient(90deg,#f59e0b,#fbbf24)'
                                : 'linear-gradient(90deg,#ef4444,#f87171)',
                            }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-emerald-400 font-medium">
                        {row.with_website.toLocaleString()} with site
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <ProgressBar value={sharePct} size="sm" color="indigo" className="w-24" />
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </GlassCard>
  );
}

interface ActivityFeedProps {
  businesses: BusinessRaw[];
  audits: AuditReportRaw[];
  loading: boolean;
}

type FeedItem = {
  id: string;
  type: 'discovery' | 'audit';
  title: string;
  subtitle: string;
  time: string;
  score?: number;
};

function ActivityFeed({ businesses, audits, loading }: ActivityFeedProps) {
  const items: FeedItem[] = useMemo(() => {
    const feed: FeedItem[] = [];
    businesses.slice(0, 5).forEach((b) => {
      feed.push({
        id: b.id,
        type: 'discovery',
        title: b.name,
        subtitle: [b.city, b.state, b.industry].filter(Boolean).join(' — '),
        time: b.discovered_at ?? b.created_at,
        score: b.opportunity_score ?? undefined,
      });
    });
    audits.slice(0, 5).forEach((a) => {
      feed.push({
        id: a.id,
        type: 'audit',
        title: a.website_url ?? `Audit ${a.id.slice(0, 8)}`,
        subtitle: `Audit ${a.status}`,
        time: a.completed_at ?? a.created_at,
        score: a.overall_score ?? undefined,
      });
    });
    return feed.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime()).slice(0, 10);
  }, [businesses, audits]);

  const typeConfig = {
    discovery: { color: '#6366f1', bg: 'rgba(99,102,241,0.12)', icon: <Building2 size={12} /> },
    audit: { color: '#10b981', bg: 'rgba(16,185,129,0.12)', icon: <Activity size={12} /> },
  };

  return (
    <GlassCard padding="none" className="h-full">
      <div className="flex items-center gap-2 px-5 pt-5 pb-3">
        <Activity size={16} className="text-indigo-400" />
        <h3 className="text-sm font-semibold text-white">Recent Activity</h3>
        <span
          className="ml-auto w-2 h-2 rounded-full"
          style={{ background: '#10b981', boxShadow: '0 0 6px #10b981' }}
        />
        <span className="text-xs text-emerald-400">Live</span>
      </div>

      <div className="px-3 pb-4 space-y-1 overflow-y-auto" style={{ maxHeight: 420 }}>
        {loading
          ? Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-14 skeleton rounded-lg" />
            ))
          : items.map((item, i) => {
              const cfg = typeConfig[item.type];
              let timeStr = 'recently';
              try {
                const diff = Date.now() - new Date(item.time).getTime();
                const mins = Math.floor(diff / 60000);
                if (mins < 1) timeStr = 'just now';
                else if (mins < 60) timeStr = `${mins}m ago`;
                else if (mins < 1440) timeStr = `${Math.floor(mins / 60)}h ago`;
                else timeStr = `${Math.floor(mins / 1440)}d ago`;
              } catch { /* keep 'recently' */ }
              return (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex items-start gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors hover:bg-white/5"
                >
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                    style={{ background: cfg.bg, color: cfg.color }}
                  >
                    {cfg.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{item.title}</p>
                    <p className="text-xs text-slate-500 truncate">{item.subtitle}</p>
                  </div>
                  <div className="flex flex-col items-end gap-0.5 flex-shrink-0">
                    {item.score !== undefined && (
                      <span
                        className="text-xs font-bold px-1.5 py-0.5 rounded"
                        style={{
                          background: item.score >= 70 ? 'rgba(16,185,129,0.15)' : item.score >= 50 ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)',
                          color: item.score >= 70 ? '#34d399' : item.score >= 50 ? '#fbbf24' : '#f87171',
                        }}
                      >
                        {item.score}
                      </span>
                    )}
                    <span className="text-[10px] text-slate-600">{timeStr}</span>
                  </div>
                </motion.div>
              );
            })}
      </div>
    </GlassCard>
  );
}

// ─── hero stat value (CountUp + change badge) ─────────────────────────────────

interface HeroStatValueProps {
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  change?: number;
}

function HeroStatValue({ value, prefix = '', suffix = '', decimals = 0, change }: HeroStatValueProps) {
  const isPositive = change !== undefined && change > 0;
  const isNegative = change !== undefined && change < 0;
  const isNeutral = change === 0;

  return (
    <div className="flex items-end justify-between">
      <span className="text-2xl font-bold text-white">
        {prefix}
        <CountUp end={value} duration={1.5} decimals={decimals} separator="," useEasing />
        {suffix}
      </span>
      {change !== undefined && (
        <div
          className={`flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-full ${
            isPositive ? 'text-emerald-400' : isNegative ? 'text-red-400' : 'text-slate-400'
          }`}
          style={{
            background: isPositive
              ? 'rgba(16,185,129,0.12)'
              : isNegative
              ? 'rgba(239,68,68,0.12)'
              : 'rgba(82,82,91,0.15)',
          }}
        >
          {isPositive && <TrendingUp size={12} />}
          {isNegative && <TrendingDown size={12} />}
          {isNeutral && <Minus size={12} />}
          <span>{isPositive ? '+' : ''}{change}%</span>
        </div>
      )}
    </div>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [period, setPeriod] = useState<TimePeriod>('30d');

  const { data: kpis, isLoading: kpisLoading, refetch, isFetching } = useQuery<AnalyticsDashboardRaw>({
    queryKey: ['analytics', 'dashboard'],
    queryFn: () => analyticsApi.dashboard(),
    staleTime: 60_000,
    retry: 1,
  });

  const { data: industriesData } = useQuery({
    queryKey: ['analytics', 'industries'],
    queryFn: () => analyticsApi.industries({ limit: 8 }),
    staleTime: 60_000,
  });

  const { data: geoData } = useQuery({
    queryKey: ['analytics', 'geography'],
    queryFn: () => analyticsApi.geography({ group_by: 'city', limit: 10 }),
    staleTime: 60_000,
  });

  const { data: trendData } = useQuery({
    queryKey: ['analytics', 'trends', 90],
    queryFn: () => analyticsApi.trends({ days: 90 }),
    staleTime: 60_000,
  });

  const { data: scoresData } = useQuery({
    queryKey: ['analytics', 'scores-distribution'],
    queryFn: () => analyticsApi.scoresDistribution({ buckets: 5 }),
    staleTime: 60_000,
  });

  const { data: recentBusinesses } = useQuery({
    queryKey: ['businesses', 'recent'],
    queryFn: () => businessesApi.list({ page: 1, page_size: 5 }),
    staleTime: 60_000,
  });

  const { data: recentAudits } = useQuery({
    queryKey: ['audits', 'recent'],
    queryFn: () => auditsApi.list({ page: 1, page_size: 5 }),
    staleTime: 60_000,
  });

  const loading = kpisLoading;

  return (
    <DashboardLayout>
      <motion.div
        initial="hidden"
        animate="show"
        variants={stagger}
        className="p-6 space-y-6 min-h-full"
        style={{
          background: 'linear-gradient(180deg, rgba(8,8,20,0) 0%, rgba(6,6,16,0.4) 100%)',
        }}
      >
        {/* ── Hero header ───────────────────────────────────────────────── */}
        <motion.div variants={fadeUp} className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">
              Executive{' '}
              <span
                className="bg-clip-text text-transparent"
                style={{ backgroundImage: 'linear-gradient(135deg, #6366f1 0%, #a78bfa 50%, #c084fc 100%)' }}
              >
                Dashboard
              </span>
            </h1>
            <p className="text-sm text-slate-400">
              Real-time business intelligence &amp; opportunity pipeline overview
            </p>
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-slate-300 transition-all hover:text-white disabled:opacity-50"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
            Refresh
          </button>
        </motion.div>

        {/* ── Hero stat cards ───────────────────────────────────────────── */}
        <motion.div variants={stagger} className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">

          {/* Total Businesses */}
          <motion.div variants={fadeUp}>
            {loading ? (
              <StatSkeleton />
            ) : (
              <div
                className="relative rounded-xl overflow-hidden p-5"
                style={{
                  background: 'rgba(14,14,32,0.7)',
                  backdropFilter: 'blur(16px)',
                  border: '1px solid rgba(99,102,241,0.2)',
                  boxShadow: '0 8px 32px rgba(0,0,0,0.3), 0 0 20px rgba(99,102,241,0.12)',
                }}
              >
                <div className="flex items-start justify-between mb-4">
                  <p className="text-sm text-slate-400 font-medium">Total Businesses</p>
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(99,102,241,0.15)' }}
                  >
                    <Building2 size={18} className="text-indigo-400" />
                  </div>
                </div>
                <HeroStatValue value={kpis?.total_businesses ?? 0} />
                <div className="absolute bottom-0 left-0 right-0 h-0.5"
                  style={{ background: 'linear-gradient(90deg, transparent, rgba(99,102,241,0.6), transparent)' }} />
              </div>
            )}
          </motion.div>

          {/* Websites Audited */}
          <motion.div variants={fadeUp}>
            {loading ? (
              <StatSkeleton />
            ) : (
              <div
                className="relative rounded-xl overflow-hidden p-5"
                style={{
                  background: 'rgba(14,14,32,0.7)',
                  backdropFilter: 'blur(16px)',
                  border: '1px solid rgba(16,185,129,0.2)',
                  boxShadow: '0 8px 32px rgba(0,0,0,0.3), 0 0 20px rgba(16,185,129,0.1)',
                }}
              >
                <div className="flex items-start justify-between mb-4">
                  <p className="text-sm text-slate-400 font-medium">Websites Audited</p>
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(16,185,129,0.15)' }}
                  >
                    <Globe size={18} className="text-emerald-400" />
                  </div>
                </div>
                <HeroStatValue value={kpis?.total_audited ?? 0} />
                <div className="absolute bottom-0 left-0 right-0 h-0.5"
                  style={{ background: 'linear-gradient(90deg, transparent, rgba(16,185,129,0.6), transparent)' }} />
              </div>
            )}
          </motion.div>

          {/* Without Websites */}
          <motion.div variants={fadeUp}>
            {loading ? (
              <StatSkeleton />
            ) : (
              <div
                className="relative rounded-xl overflow-hidden p-5"
                style={{
                  background: 'rgba(14,14,32,0.7)',
                  backdropFilter: 'blur(16px)',
                  border: '1px solid rgba(245,158,11,0.2)',
                  boxShadow: '0 8px 32px rgba(0,0,0,0.3), 0 0 20px rgba(245,158,11,0.1)',
                }}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="text-sm text-slate-400 font-medium">Without Websites</p>
                    <span
                      className="inline-block mt-0.5 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
                      style={{ background: 'rgba(245,158,11,0.15)', color: '#fbbf24' }}
                    >
                      Opportunity
                    </span>
                  </div>
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(245,158,11,0.15)' }}
                  >
                    <AlertTriangle size={18} className="text-amber-400" />
                  </div>
                </div>
                <HeroStatValue value={kpis?.total_without_website ?? 0} />
                <div className="absolute bottom-0 left-0 right-0 h-0.5"
                  style={{ background: 'linear-gradient(90deg, transparent, rgba(245,158,11,0.6), transparent)' }} />
              </div>
            )}
          </motion.div>

          {/* Revenue Potential */}
          <motion.div variants={fadeUp}>
            {loading ? (
              <StatSkeleton />
            ) : (
              <div
                className="relative rounded-xl overflow-hidden p-5"
                style={{
                  background: 'rgba(14,14,32,0.7)',
                  backdropFilter: 'blur(16px)',
                  border: '1px solid rgba(167,139,250,0.2)',
                  boxShadow: '0 8px 32px rgba(0,0,0,0.3), 0 0 20px rgba(167,139,250,0.12)',
                }}
              >
                <div className="flex items-start justify-between mb-4">
                  <p className="text-sm text-slate-400 font-medium">Revenue Potential</p>
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(167,139,250,0.15)' }}
                  >
                    <DollarSign size={18} className="text-purple-400" />
                  </div>
                </div>
                <HeroStatValue
                  value={kpis ? (kpis.avg_revenue_potential ?? 0) / 1_000 : 0}
                  prefix="$"
                  suffix="k avg"
                  decimals={1}
                />
                <div className="absolute bottom-0 left-0 right-0 h-0.5"
                  style={{ background: 'linear-gradient(90deg, transparent, rgba(167,139,250,0.6), transparent)' }} />
              </div>
            )}
          </motion.div>
        </motion.div>

        {/* ── Charts row ────────────────────────────────────────────────── */}
        <motion.div variants={fadeUp} className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <ScoreDistChart data={scoresData?.histogram ?? []} loading={loading} />
          <IndustryPieChart data={industriesData?.items ?? []} loading={loading} />
        </motion.div>

        {/* ── Revenue trend (full width) ────────────────────────────────── */}
        <motion.div variants={fadeUp}>
          <RevenueTrendChart
            trend={trendData}
            loading={loading}
            period={period}
            onPeriodChange={setPeriod}
          />
        </motion.div>

        {/* ── Bottom row: geo table + activity feed ─────────────────────── */}
        <motion.div variants={fadeUp} className="grid grid-cols-1 xl:grid-cols-3 gap-5">
          <div className="xl:col-span-2">
            <GeoTable data={geoData?.items ?? []} loading={loading} />
          </div>
          <div>
            <ActivityFeed
              businesses={recentBusinesses?.items ?? []}
              audits={recentAudits?.items ?? []}
              loading={loading}
            />
          </div>
        </motion.div>

        {/* ── Footer note ───────────────────────────────────────────────── */}
        <motion.div variants={fadeUp} className="text-center pb-2">
          <p className="text-xs text-slate-600">
            Data refreshes every 60 seconds &nbsp;·&nbsp; Last updated <ClientTime />
          </p>
        </motion.div>
      </motion.div>
    </DashboardLayout>
  );
}
