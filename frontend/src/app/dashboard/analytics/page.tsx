'use client';

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api';
import type { IndustryBreakdownRaw, GeographyItemRaw } from '@/lib/api';
import { motion } from 'framer-motion';
import {
  BarChart3,
  TrendingUp,
  Globe,
  Building2,
  ChevronUp,
  ChevronDown,
  Activity,
  DollarSign,
  Target,
  Layers,
} from 'lucide-react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { cn, formatCurrency } from '@/lib/utils';
import GlassCard from '@/components/ui/GlassCard';
import StatCard from '@/components/ui/StatCard';

// ─── Types ────────────────────────────────────────────────────────────────────

type TimeRange = '7D' | '30D' | '90D' | '1Y' | 'Custom';

type SortKey = 'country' | 'businesses' | 'avgScore' | 'revenue';
type SortDir = 'asc' | 'desc';

// ─── Data Generators (kept for opportunity trend only) ────────────────────────

function generateOpportunityTrend(days: number) {
  let score = 72;
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(Date.now() - (days - 1 - i) * 86400000);
    score = Math.min(100, Math.max(40, score + (Math.random() - 0.45) * 4));
    return {
      date: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      avgScore: Math.round(score),
      highPriority: Math.floor(Math.random() * 25 + 5),
    };
  });
}

const INDUSTRY_COLORS = ['#6366f1', '#a855f7', '#ec4899', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#64748b'];

// ─── Custom Tooltip ───────────────────────────────────────────────────────────

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="px-3 py-2.5 rounded-xl text-xs"
      style={{
        background: 'rgba(18,18,40,0.97)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(255,255,255,0.1)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
      }}
    >
      {label && <div className="text-slate-400 mb-2 font-medium">{label}</div>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-slate-400 capitalize">{p.name}:</span>
          <span className="text-white font-semibold">{p.value}</span>
        </div>
      ))}
    </div>
  );
}

function RevenueTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="px-3 py-2.5 rounded-xl text-xs"
      style={{
        background: 'rgba(18,18,40,0.97)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(255,255,255,0.1)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
      }}
    >
      <div className="text-slate-400 mb-1">{label}</div>
      <div className="text-white font-semibold">{formatCurrency(payload[0].value * 1000)}</div>
    </div>
  );
}

// ─── Score-based bar color ────────────────────────────────────────────────────

function scoreBarColor(score: number): string {
  if (score >= 75) return '#10b981';
  if (score >= 60) return '#6366f1';
  if (score >= 45) return '#f59e0b';
  return '#ef4444';
}

// ─── Sortable Country Table ───────────────────────────────────────────────────

interface CountryRow {
  country: string;
  flag?: string;
  businesses: number;
  avgScore: number;
  revenue: number;
}

function CountryTable({ data }: { data: CountryRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('businesses');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const sorted = useMemo(() => {
    return [...data].sort((a, b) => {
      if (sortKey === 'country') {
        return sortDir === 'asc'
          ? a.country.localeCompare(b.country)
          : b.country.localeCompare(a.country);
      }
      const aVal = a[sortKey] as number;
      const bVal = b[sortKey] as number;
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    });
  }, [data, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const SortIcon = ({ col }: { col: SortKey }) =>
    sortKey === col ? (
      sortDir === 'asc' ? (
        <ChevronUp size={12} className="text-indigo-400" />
      ) : (
        <ChevronDown size={12} className="text-indigo-400" />
      )
    ) : (
      <div className="w-3 h-3" />
    );

  const TH = ({ col, label, align = 'left' }: { col: SortKey; label: string; align?: 'left' | 'right' }) => (
    <th
      className={cn(
        'px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer hover:text-slate-300 transition-colors select-none',
        align === 'right' && 'text-right'
      )}
      onClick={() => toggleSort(col)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <SortIcon col={col} />
      </span>
    </th>
  );

  const maxBusinesses = useMemo(() => Math.max(...data.map((r) => r.businesses), 1), [data]);

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
            <TH col="country" label="Country" />
            <TH col="businesses" label="Businesses" />
            <TH col="avgScore" label="Avg. Score" />
            <TH col="revenue" label="Revenue Potential" align="right" />
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {sorted.map((row, i) => (
            <motion.tr
              key={row.country}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className="hover:bg-white/3 transition-colors"
            >
              <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                  {row.flag && <span className="text-xl">{row.flag}</span>}
                  <span className="text-sm font-medium text-white">{row.country}</span>
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex-1 max-w-24 h-1.5 rounded-full bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-indigo-500"
                      style={{ width: `${(row.businesses / maxBusinesses) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm text-slate-300">{row.businesses}</span>
                </div>
              </td>
              <td className="px-4 py-3">
                <span
                  className={cn(
                    'text-sm font-bold',
                    row.avgScore >= 75
                      ? 'text-emerald-400'
                      : row.avgScore >= 65
                      ? 'text-indigo-400'
                      : 'text-amber-400'
                  )}
                >
                  {row.avgScore}
                </span>
              </td>
              <td className="px-4 py-3 text-right">
                <span className="text-sm font-semibold text-white">
                  {formatCurrency(row.revenue, { notation: 'compact' })}
                </span>
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Score Distribution Histogram ────────────────────────────────────────────

interface HistogramBar { range: string; count: number; }

function ScoreHistogram({ data }: { data: HistogramBar[] }) {
  const max = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="flex items-end justify-between gap-2 h-32 px-2">
      {data.map((bar, i) => {
        const pct = (bar.count / max) * 100;
        const score = (i + 1) * 10;
        const color =
          score >= 80
            ? '#10b981'
            : score >= 60
            ? '#6366f1'
            : score >= 40
            ? '#f59e0b'
            : '#ef4444';
        return (
          <div key={bar.range} className="flex-1 flex flex-col items-center gap-1 group">
            <div className="relative w-full">
              <motion.div
                className="w-full rounded-t-sm"
                style={{ background: color, height: `${pct * 1.28}px`, opacity: 0.8 }}
                initial={{ scaleY: 0, originY: 1 }}
                animate={{ scaleY: 1 }}
                transition={{ delay: i * 0.05, duration: 0.4 }}
              />
              <div
                className="absolute -top-8 left-1/2 -translate-x-1/2 px-2 py-1 rounded text-xs text-white whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
                style={{ background: 'rgba(18,18,40,0.97)', border: '1px solid rgba(255,255,255,0.1)' }}
              >
                {bar.count}
              </div>
            </div>
            <span className="text-xs text-slate-600 rotate-[-30deg] origin-top mt-1">{bar.range}</span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>('30D');

  const dayCount = { '7D': 7, '30D': 30, '90D': 90, '1Y': 365, Custom: 30 }[timeRange];
  const opportunityData = useMemo(() => generateOpportunityTrend(Math.min(dayCount, 60)), [timeRange]);

  // ── Real API queries ──────────────────────────────────────────────────────
  const { data: dashboardData } = useQuery({
    queryKey: ['analytics', 'dashboard'],
    queryFn: () => analyticsApi.dashboard(),
    staleTime: 60_000,
  });

  const { data: industriesData } = useQuery({
    queryKey: ['analytics', 'industries', 8],
    queryFn: () => analyticsApi.industries({ limit: 8 }),
    staleTime: 60_000,
  });

  const { data: geographyData } = useQuery({
    queryKey: ['analytics', 'geography', 'country', 8],
    queryFn: () => analyticsApi.geography({ group_by: 'country', limit: 8 }),
    staleTime: 60_000,
  });

  const { data: trendsData } = useQuery({
    queryKey: ['analytics', 'trends', dayCount],
    queryFn: () => analyticsApi.trends({ days: dayCount }),
    staleTime: 60_000,
  });

  const { data: scoresDistData } = useQuery({
    queryKey: ['analytics', 'scores-distribution'],
    queryFn: () => analyticsApi.scoresDistribution({ buckets: 10 }),
    staleTime: 60_000,
  });

  const { data: revenueData } = useQuery({
    queryKey: ['analytics', 'revenue', 6],
    queryFn: () => analyticsApi.revenue({ limit: 6 }),
    staleTime: 60_000,
  });

  // ── Derived data ──────────────────────────────────────────────────────────

  // Discoveries chart: merge businesses_discovered + audits_completed by date
  const discoveriesData = useMemo(() => {
    if (!trendsData) return [];
    const byDate: Record<string, { date: string; discoveries: number; audited: number }> = {};
    for (const item of trendsData.businesses_discovered ?? []) {
      const d = new Date(item.date);
      const label = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      byDate[item.date] = { date: label, discoveries: item.count, audited: 0 };
    }
    for (const item of trendsData.audits_completed ?? []) {
      const d = new Date(item.date);
      const label = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      if (byDate[item.date]) {
        byDate[item.date].audited = item.count;
      } else {
        byDate[item.date] = { date: label, discoveries: 0, audited: item.count };
      }
    }
    return Object.keys(byDate)
      .sort()
      .map((k) => byDate[k]);
  }, [trendsData]);

  // Industry pie data
  const industryPieData = useMemo(() => {
    return (industriesData?.items ?? []).map((item: IndustryBreakdownRaw, i: number) => ({
      name: item.industry,
      value: item.count,
      color: INDUSTRY_COLORS[i % INDUSTRY_COLORS.length],
    }));
  }, [industriesData]);

  // Industry scores
  const industryScores = useMemo(() => {
    return (industriesData?.items ?? []).map((item: IndustryBreakdownRaw) => ({
      industry: item.industry,
      avgScore: Math.round(item.avg_opportunity_score ?? item.avg_score ?? 0),
    }));
  }, [industriesData]);

  // Geography table data
  const countryTableData = useMemo(() => {
    return (geographyData?.items ?? []).map((item: GeographyItemRaw) => ({
      country: item.location,
      businesses: item.count,
      avgScore: Math.round(item.avg_score ?? 0),
      revenue: 0,
    }));
  }, [geographyData]);

  // Revenue bar chart
  const revenueByIndustry = useMemo(() => {
    return (revenueData?.items ?? []).map((item) => ({
      name: item.industry,
      revenue: (item.total_revenue_potential ?? 0) / 1000,
    }));
  }, [revenueData]);

  // Score histogram
  const histogramData = useMemo((): HistogramBar[] => {
    return (scoresDistData?.histogram ?? []).map((item) => ({
      range: item.label,
      count: item.count,
    }));
  }, [scoresDistData]);

  // KPI values
  const kpiTotalBusinesses = dashboardData?.total_businesses ?? 0;
  const kpiAvgScore = dashboardData?.avg_opportunity_score != null
    ? Math.round(dashboardData.avg_opportunity_score)
    : 0;
  const kpiRevenuePipeline = dashboardData?.avg_revenue_potential != null
    ? Math.round((dashboardData.avg_revenue_potential / 1_000_000) * 10) / 10
    : 0;
  const kpiNewThisPeriod = dashboardData?.businesses_added_last_30_days ?? 0;

  const TIME_RANGES: TimeRange[] = ['7D', '30D', '90D', '1Y', 'Custom'];

  return (
    <div className="min-h-full p-6 space-y-6">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, rgba(99,102,241,0.3), rgba(168,85,247,0.3))',
              border: '1px solid rgba(99,102,241,0.3)',
            }}
          >
            <BarChart3 size={20} className="text-indigo-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Analytics Center</h1>
            <p className="text-sm text-slate-400">Deep insights and discovery trends</p>
          </div>
        </div>

        {/* Time Range Tabs */}
        <div
          className="flex rounded-xl overflow-hidden border border-white/10"
          style={{ background: 'rgba(255,255,255,0.03)' }}
        >
          {TIME_RANGES.map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={cn(
                'px-4 py-2 text-sm font-medium transition-all',
                timeRange === range
                  ? 'text-white'
                  : 'text-slate-400 hover:text-slate-300'
              )}
              style={
                timeRange === range
                  ? {
                      background: 'linear-gradient(135deg, rgba(99,102,241,0.4), rgba(168,85,247,0.3))',
                      borderRight: '1px solid rgba(99,102,241,0.3)',
                    }
                  : {}
              }
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* ── KPI Stat Cards ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Businesses"
          value={kpiTotalBusinesses}
          change={12}
          icon={<Building2 size={16} />}
        />
        <StatCard
          label="Avg Opportunity Score"
          value={kpiAvgScore}
          suffix="/100"
          change={3}
          icon={<Target size={16} />}
          iconColor="text-emerald-400"
        />
        <StatCard
          label="Revenue Pipeline"
          value={kpiRevenuePipeline}
          prefix="$"
          suffix="M"
          decimals={1}
          change={18}
          icon={<DollarSign size={16} />}
          iconColor="text-emerald-400"
        />
        <StatCard
          label="New This Period"
          value={kpiNewThisPeriod}
          change={7}
          icon={<Activity size={16} />}
          iconColor="text-purple-400"
        />
      </div>

      {/* ── Charts 2x2 Grid ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Discoveries Over Time - Line */}
        <GlassCard>
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-sm font-semibold text-white">Discoveries Over Time</h3>
              <p className="text-xs text-slate-500 mt-0.5">Businesses found and audited</p>
            </div>
            <TrendingUp size={16} className="text-indigo-400" />
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={discoveriesData} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#64748b', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval={Math.floor(discoveriesData.length / 5)}
              />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip content={<ChartTooltip />} />
              <Line
                type="monotone"
                dataKey="discoveries"
                stroke="#6366f1"
                strokeWidth={2}
                dot={false}
                name="Discoveries"
              />
              <Line
                type="monotone"
                dataKey="audited"
                stroke="#a855f7"
                strokeWidth={2}
                dot={false}
                strokeDasharray="5 3"
                name="Audited"
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="flex items-center gap-5 mt-3">
            <div className="flex items-center gap-2">
              <div className="w-6 h-0.5 bg-indigo-500 rounded" />
              <span className="text-xs text-slate-500">Discoveries</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-6 h-0.5 bg-purple-500 rounded border-dashed" />
              <span className="text-xs text-slate-500">Audited</span>
            </div>
          </div>
        </GlassCard>

        {/* Industry Distribution - Donut */}
        <GlassCard>
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-sm font-semibold text-white">Industry Distribution</h3>
              <p className="text-xs text-slate-500 mt-0.5">Breakdown by sector</p>
            </div>
            <Layers size={16} className="text-purple-400" />
          </div>
          <div className="flex items-center gap-4">
            <ResponsiveContainer width={160} height={160}>
              <PieChart>
                <Pie
                  data={industryPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={70}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {industryPieData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) =>
                    active && payload?.length ? (
                      <div
                        className="px-3 py-2 rounded-xl text-xs"
                        style={{ background: 'rgba(18,18,40,0.97)', border: '1px solid rgba(255,255,255,0.1)' }}
                      >
                        <span className="text-slate-400">{payload[0].name}: </span>
                        <span className="text-white font-bold">{payload[0].value}</span>
                      </div>
                    ) : null
                  }
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex-1 space-y-2">
              {industryPieData.map((item) => (
                <div key={item.name} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: item.color }} />
                    <span className="text-xs text-slate-400 truncate">{item.name}</span>
                  </div>
                  <span className="text-xs font-semibold text-slate-300">{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>

        {/* Opportunity Score Trend - Area */}
        <GlassCard>
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-sm font-semibold text-white">Opportunity Score Trend</h3>
              <p className="text-xs text-slate-500 mt-0.5">Average score over time</p>
            </div>
            <Target size={16} className="text-emerald-400" />
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={opportunityData} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
              <defs>
                <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="highGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#64748b', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval={Math.floor(opportunityData.length / 5)}
              />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} axisLine={false} domain={[0, 100]} />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="avgScore"
                stroke="#6366f1"
                strokeWidth={2}
                fill="url(#scoreGradient)"
                name="Avg Score"
              />
              <Area
                type="monotone"
                dataKey="highPriority"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#highGradient)"
                name="High Priority"
              />
            </AreaChart>
          </ResponsiveContainer>
        </GlassCard>

        {/* Revenue by Country - Horizontal Bar */}
        <GlassCard>
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-sm font-semibold text-white">Revenue Potential by Country</h3>
              <p className="text-xs text-slate-500 mt-0.5">Pipeline value ($K)</p>
            </div>
            <DollarSign size={16} className="text-amber-400" />
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={revenueByIndustry}
              layout="vertical"
              margin={{ top: 0, right: 10, bottom: 0, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
              <XAxis type="number" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={70}
              />
              <Tooltip content={<RevenueTooltip />} />
              <Bar dataKey="revenue" radius={[0, 4, 4, 0]} name="Revenue">
                {revenueByIndustry.map((_, i) => (
                  <Cell
                    key={i}
                    fill={`rgba(99,102,241,${1 - i * 0.12})`}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </GlassCard>
      </div>

      {/* ── Geographic Analysis ──────────────────────────────────────────── */}
      <GlassCard>
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <Globe size={18} className="text-indigo-400" />
            <div>
              <h3 className="text-sm font-semibold text-white">Geographic Analysis</h3>
              <p className="text-xs text-slate-500 mt-0.5">Performance breakdown by country</p>
            </div>
          </div>
        </div>
        <CountryTable data={countryTableData} />
      </GlassCard>

      {/* ── Industry Deep Dive ───────────────────────────────────────────── */}
      <GlassCard>
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <Building2 size={18} className="text-purple-400" />
            <div>
              <h3 className="text-sm font-semibold text-white">Industry Deep Dive</h3>
              <p className="text-xs text-slate-500 mt-0.5">Average opportunity score by sector</p>
            </div>
          </div>
        </div>
        <div className="space-y-3">
          {industryScores.map((item, i) => (
            <motion.div
              key={item.industry}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06 }}
              className="flex items-center gap-4"
            >
              <div className="w-24 text-xs text-slate-400 flex-shrink-0 text-right">
                {item.industry}
              </div>
              <div className="flex-1 h-7 rounded-lg overflow-hidden relative"
                style={{ background: 'rgba(255,255,255,0.04)' }}>
                <motion.div
                  className="h-full rounded-lg flex items-center pl-3"
                  initial={{ width: 0 }}
                  animate={{ width: `${item.avgScore}%` }}
                  transition={{ delay: i * 0.06 + 0.2, duration: 0.6, ease: 'easeOut' }}
                  style={{ background: `linear-gradient(90deg, ${scoreBarColor(item.avgScore)}44, ${scoreBarColor(item.avgScore)})` }}
                >
                  <span className="text-xs font-bold text-white">{item.avgScore}</span>
                </motion.div>
              </div>
            </motion.div>
          ))}
        </div>
      </GlassCard>

      {/* ── Score Distribution ───────────────────────────────────────────── */}
      <GlassCard>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <BarChart3 size={18} className="text-amber-400" />
            <div>
              <h3 className="text-sm font-semibold text-white">Score Distribution</h3>
              <p className="text-xs text-slate-500 mt-0.5">How opportunity scores are distributed across all businesses</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-emerald-500" />High (80+)</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-indigo-500" />Good (60-79)</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-500" />Fair (40-59)</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-500" />Poor (&lt;40)</span>
          </div>
        </div>
        <ScoreHistogram data={histogramData} />
        <div className="mt-6 pt-4 border-t border-white/5 grid grid-cols-4 gap-4">
          {[
            { label: 'Median Score', value: '73', sub: 'All businesses' },
            { label: 'High Priority', value: '308', sub: 'Score 80+' },
            { label: 'Needs Work', value: '521', sub: 'Score 40-79' },
            { label: 'Critical', value: '152', sub: 'Score <40' },
          ].map((s) => (
            <div key={s.label} className="text-center">
              <div className="text-xl font-bold text-white">{s.value}</div>
              <div className="text-xs font-medium text-slate-400 mt-0.5">{s.label}</div>
              <div className="text-xs text-slate-600">{s.sub}</div>
            </div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
