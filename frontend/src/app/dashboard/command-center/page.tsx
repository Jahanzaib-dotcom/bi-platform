'use client';

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from 'recharts';
import {
  Activity,
  Cpu,
  MemoryStick,
  Layers,
  Zap,
  Users,
  Play,
  Pause,
  Square,
  Trash2,
  Plus,
  ChevronDown,
  ChevronUp,
  Filter,
  ScrollText,
  Search,
  X,
  RefreshCw,
  Globe,
  MapPin,
  Database,
  SlidersHorizontal,
} from 'lucide-react';
import GlassCard from '@/components/ui/GlassCard';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useSystemStore } from '@/store';

// =========================================================================
// TYPES
// =========================================================================

type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'SUCCESS';

interface LogEntry {
  id: string;
  level: LogLevel;
  message: string;
  timestamp: string;
  source?: string;
}

interface ActiveJob {
  id: string;
  name: string;
  provider: string;
  progress: number;
  status: 'running' | 'paused' | 'failed' | 'queued';
  eta: string;
  discovered: number;
  total: number;
  location: string;
  startedAt: string;
}

interface MetricPoint {
  t: string;
  v: number;
}

interface LiveMetrics {
  discoveryRate: MetricPoint[];
  auditRate: MetricPoint[];
  errorRate: MetricPoint[];
  queueDepth: MetricPoint[];
}

interface SystemStats {
  cpu: number;
  memory: number;
  queue: number;
  workers: number;
  msgPerSec: number;
}

// =========================================================================
// MOCK DATA GENERATORS
// =========================================================================

const PROVIDERS = ['DuckDuckGo', 'Nominatim', 'SerpAPI', 'Bing Maps', 'Yelp'];
const LOCATIONS = [
  'New York, US', 'Los Angeles, US', 'Chicago, US', 'Houston, US',
  'London, UK', 'Paris, FR', 'Berlin, DE', 'Tokyo, JP',
];
const JOB_NAMES = [
  'Restaurants NYC Q3', 'Retail Audit Chicago', 'Healthcare LA Sweep',
  'Hotels London Scan', 'Auto Services Berlin', 'Fitness NYC Discovery',
];

function randBetween(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function fmtTime(date = new Date()) {
  const h = String(date.getHours()).padStart(2, '0');
  const m = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

function generateInitialJobs(): ActiveJob[] {
  return Array.from({ length: 3 }, (_, i) => {
    const total = randBetween(200, 5000);
    const discovered = randBetween(0, total);
    const status: ActiveJob['status'] = i === 2 ? 'paused' : 'running';
    const secsLeft = Math.floor((total - discovered) / (Math.random() * 5 + 1));
    const mins = Math.floor(secsLeft / 60);
    return {
      id: `job-${i + 1}`,
      name: JOB_NAMES[i],
      provider: PROVIDERS[i % PROVIDERS.length],
      progress: Math.round((discovered / total) * 100),
      status,
      eta: mins > 0 ? `${mins}m left` : '<1m left',
      discovered,
      total,
      location: LOCATIONS[i],
      startedAt: new Date(Date.now() - randBetween(60000, 7200000)).toISOString(),
    };
  });
}

function generateInitialLogs(): LogEntry[] {
  const levels: LogLevel[] = ['INFO', 'INFO', 'INFO', 'SUCCESS', 'WARN', 'ERROR'];
  const messages = [
    ['INFO', 'Worker #3 started job "Restaurants NYC Q3"', 'worker-3'],
    ['SUCCESS', 'Discovered 148 businesses in Manhattan district', 'discovery'],
    ['INFO', 'Rate limiter: DuckDuckGo backoff 2.4s', 'rate-limiter'],
    ['WARN', 'SerpAPI quota at 78% — throttling requests', 'api-guard'],
    ['INFO', 'Nominatim geocoder returned 42 results', 'geocoder'],
    ['SUCCESS', 'Audit completed for "NYC Diner Co." — score 73', 'auditor'],
    ['ERROR', 'Failed to fetch page 4 of Yelp results: 429 Too Many Requests', 'scraper'],
    ['INFO', 'Queue depth: 512 pending items', 'queue'],
    ['INFO', 'Worker #1 heartbeat OK', 'monitor'],
    ['SUCCESS', 'Export job #44 completed — 3,221 rows', 'exporter'],
  ] as [LogLevel, string, string][];
  return messages.map(([level, message, source], i) => ({
    id: `log-init-${i}`,
    level,
    message,
    source,
    timestamp: fmtTime(new Date(Date.now() - (messages.length - i) * 4500)),
  }));
}

function generateInitialMetrics(): LiveMetrics {
  const now = Date.now();
  const points = (gen: () => number) =>
    Array.from({ length: 30 }, (_, i) => ({
      t: fmtTime(new Date(now - (30 - i) * 5000)),
      v: gen(),
    }));
  return {
    discoveryRate: points(() => randBetween(8, 42)),
    auditRate: points(() => randBetween(1, 12)),
    errorRate: points(() => parseFloat((Math.random() * 4).toFixed(1))),
    queueDepth: points(() => randBetween(80, 620)),
  };
}

function generateInitialStats(): SystemStats {
  return {
    cpu: randBetween(28, 72),
    memory: randBetween(40, 78),
    queue: randBetween(80, 600),
    workers: randBetween(3, 8),
    msgPerSec: randBetween(5, 45),
  };
}

const RANDOM_LOG_TEMPLATES: [LogLevel, string, string][] = [
  ['INFO', 'Fetching next page for job "{job}"', 'scraper'],
  ['INFO', 'Geocoding address in {location}', 'geocoder'],
  ['SUCCESS', 'Inserted {n} new businesses into DB', 'db'],
  ['WARN', 'Slow response from {provider} ({ms}ms)', 'http-client'],
  ['INFO', 'Worker #{w} processing batch #{b}', 'worker'],
  ['SUCCESS', 'Business "{biz}" scored {score}/100', 'auditor'],
  ['ERROR', 'DNS timeout for {provider} API endpoint', 'dns'],
  ['INFO', 'Rate limit window reset — resuming full speed', 'rate-limiter'],
  ['WARN', 'Duplicate detected: {biz} already indexed', 'deduper'],
  ['SUCCESS', 'Completed source {provider} for {location}', 'discovery'],
  ['INFO', 'Queue compacted — removed {n} stale items', 'queue'],
  ['INFO', 'Audit pipeline ready — {n} items queued', 'auditor'],
];

function generateRandomLog(): LogEntry {
  const tpl = RANDOM_LOG_TEMPLATES[randBetween(0, RANDOM_LOG_TEMPLATES.length - 1)];
  const msg = tpl[1]
    .replace('{job}', JOB_NAMES[randBetween(0, JOB_NAMES.length - 1)])
    .replace('{location}', LOCATIONS[randBetween(0, LOCATIONS.length - 1)])
    .replace('{n}', String(randBetween(10, 300)))
    .replace('{provider}', PROVIDERS[randBetween(0, PROVIDERS.length - 1)])
    .replace('{ms}', String(randBetween(800, 4500)))
    .replace('{w}', String(randBetween(1, 8)))
    .replace('{b}', String(randBetween(100, 999)))
    .replace('{biz}', `Business #${randBetween(1000, 9999)}`)
    .replace('{score}', String(randBetween(30, 95)));
  return {
    id: `log-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    level: tpl[0],
    message: msg,
    source: tpl[2],
    timestamp: fmtTime(),
  };
}

// =========================================================================
// LOG LEVEL STYLES
// =========================================================================

const LOG_LEVEL_STYLES: Record<LogLevel, { text: string; bg: string; dot: string }> = {
  INFO: { text: 'text-cyan-400', bg: 'bg-cyan-400/10', dot: 'bg-cyan-400' },
  WARN: { text: 'text-yellow-400', bg: 'bg-yellow-400/10', dot: 'bg-yellow-400' },
  ERROR: { text: 'text-red-400', bg: 'bg-red-400/10', dot: 'bg-red-500' },
  SUCCESS: { text: 'text-emerald-400', bg: 'bg-emerald-400/10', dot: 'bg-emerald-400' },
};

const STATUS_STYLES: Record<ActiveJob['status'], { label: string; text: string; bg: string; border: string }> = {
  running: { label: 'RUNNING', text: 'text-blue-400', bg: 'bg-blue-400/10', border: 'border-blue-400/30' },
  paused: { label: 'PAUSED', text: 'text-yellow-400', bg: 'bg-yellow-400/10', border: 'border-yellow-400/30' },
  failed: { label: 'FAILED', text: 'text-red-400', bg: 'bg-red-400/10', border: 'border-red-400/30' },
  queued: { label: 'QUEUED', text: 'text-slate-400', bg: 'bg-slate-400/10', border: 'border-slate-400/30' },
};

const STATUS_BAR_COLORS: Record<ActiveJob['status'], string> = {
  running: 'from-blue-500 to-indigo-500',
  paused: 'from-yellow-500 to-amber-500',
  failed: 'from-red-500 to-rose-500',
  queued: 'from-slate-500 to-slate-400',
};

// =========================================================================
// MINI CHART COMPONENT
// =========================================================================

interface MiniChartProps {
  data: MetricPoint[];
  label: string;
  value: string;
  unit: string;
  color: string;
  delta?: number;
}

function MiniChart({ data, label, value, unit, color, delta }: MiniChartProps) {
  const isPositive = delta !== undefined ? delta >= 0 : true;
  return (
    <GlassCard padding="none" className="overflow-hidden">
      <div className="p-4 pb-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</span>
          {delta !== undefined && (
            <span
              className={`text-xs font-semibold ${
                label === 'Error Rate' ? (isPositive ? 'text-red-400' : 'text-emerald-400') : (isPositive ? 'text-emerald-400' : 'text-red-400')
              }`}
            >
              {isPositive ? '+' : ''}{delta.toFixed(1)}%
            </span>
          )}
        </div>
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold text-white">{value}</span>
          <span className="text-sm text-slate-500">{unit}</span>
        </div>
      </div>
      <div className="h-16 mt-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`grad-${label.replace(/\s/g, '')}`} x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor={color} stopOpacity={0.4} />
                <stop offset="100%" stopColor={color} stopOpacity={1} />
              </linearGradient>
            </defs>
            <XAxis dataKey="t" hide />
            <Tooltip
              contentStyle={{
                background: 'rgba(18,18,40,0.95)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: '8px',
                fontSize: '11px',
                color: '#f8f8ff',
                padding: '4px 8px',
              }}
              formatter={(v: number) => [`${v} ${unit}`, label]}
              labelFormatter={() => ''}
            />
            <Line
              type="monotone"
              dataKey="v"
              stroke={`url(#grad-${label.replace(/\s/g, '')})`}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </GlassCard>
  );
}

// =========================================================================
// PULSING DOT
// =========================================================================

function PulsingDot({ color = 'bg-emerald-400' }: { color?: string }) {
  return (
    <span className="relative inline-flex h-3 w-3">
      <span
        className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-60 ${color}`}
      />
      <span className={`relative inline-flex rounded-full h-3 w-3 ${color}`} />
    </span>
  );
}

// =========================================================================
// JOB CARD
// =========================================================================

interface JobCardProps {
  job: ActiveJob;
  onTogglePause: (id: string) => void;
  onStop: (id: string) => void;
}

function JobCard({ job, onTogglePause, onStop }: JobCardProps) {
  const [expanded, setExpanded] = useState(false);
  const style = STATUS_STYLES[job.status];
  const barGradient = STATUS_BAR_COLORS[job.status];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.25 }}
    >
      <GlassCard
        padding="none"
        className="overflow-hidden cursor-pointer"
        hover
        onClick={() => setExpanded((e) => !e)}
      >
        {/* Progress bar strip at top */}
        <div className="h-0.5 bg-white/5">
          <motion.div
            className={`h-full bg-gradient-to-r ${barGradient}`}
            initial={false}
            animate={{ width: `${job.progress}%` }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
          />
        </div>

        <div className="p-4">
          {/* Header row */}
          <div className="flex items-center gap-3">
            {/* Status indicator */}
            {job.status === 'running' && (
              <PulsingDot color="bg-blue-400" />
            )}
            {job.status === 'paused' && (
              <span className="w-3 h-3 rounded-full bg-yellow-400 opacity-80" />
            )}
            {job.status === 'failed' && (
              <span className="w-3 h-3 rounded-full bg-red-400" />
            )}
            {job.status === 'queued' && (
              <span className="w-3 h-3 rounded-full bg-slate-400 opacity-60" />
            )}

            {/* Name + provider */}
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-white text-sm truncate">{job.name}</p>
              <p className="text-xs text-slate-500 mt-0.5">{job.provider} · {job.location}</p>
            </div>

            {/* Status badge */}
            <span
              className={`badge text-xs font-bold px-2 py-0.5 rounded-md border ${style.text} ${style.bg} ${style.border}`}
            >
              {style.label}
            </span>

            {/* Progress % */}
            <div className="text-right min-w-[48px]">
              <span className="text-sm font-bold text-white">{job.progress}%</span>
              <p className="text-xs text-slate-500">{job.eta}</p>
            </div>

            {/* Chevron */}
            <button
              onClick={(e) => { e.stopPropagation(); setExpanded((e) => !e); }}
              className="text-slate-500 hover:text-white transition-colors p-1"
            >
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>

          {/* Progress bar */}
          <div className="mt-3 h-1.5 bg-white/5 rounded-full overflow-hidden">
            <motion.div
              className={`h-full rounded-full bg-gradient-to-r ${barGradient}`}
              initial={false}
              animate={{ width: `${job.progress}%` }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
            />
          </div>

          {/* Stats row */}
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-slate-500">
              {job.discovered.toLocaleString()} / {job.total.toLocaleString()} businesses
            </span>
            <span className="text-xs text-slate-500">
              Started {fmtTime(new Date(job.startedAt))}
            </span>
          </div>

          {/* Expanded detail panel */}
          <AnimatePresence>
            {expanded && (
              <motion.div
                key="expanded"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div
                  className="mt-4 pt-4 border-t border-white/8 flex items-center gap-2"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    onClick={() => onTogglePause(job.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      job.status === 'paused'
                        ? 'bg-blue-500/20 text-blue-400 border border-blue-400/30 hover:bg-blue-500/30'
                        : 'bg-yellow-500/20 text-yellow-400 border border-yellow-400/30 hover:bg-yellow-500/30'
                    }`}
                  >
                    {job.status === 'paused' ? <Play size={12} /> : <Pause size={12} />}
                    {job.status === 'paused' ? 'Resume' : 'Pause'}
                  </button>
                  <button
                    onClick={() => onStop(job.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/20 text-red-400 border border-red-400/30 hover:bg-red-500/30 transition-all"
                  >
                    <Square size={12} />
                    Stop
                  </button>
                  <div className="ml-auto text-xs text-slate-500">
                    ID: <span className="font-mono text-slate-400">{job.id}</span>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </GlassCard>
    </motion.div>
  );
}

// =========================================================================
// LOG TERMINAL
// =========================================================================

interface LogFeedProps {
  logs: LogEntry[];
}

function LogFeed({ logs }: LogFeedProps) {
  const [filter, setFilter] = useState<LogLevel | 'ALL'>('ALL');
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(
    () => (filter === 'ALL' ? logs : logs.filter((l) => l.level === filter)),
    [logs, filter]
  );

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [filtered.length, autoScroll]);

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40);
  }, []);

  const levels: (LogLevel | 'ALL')[] = ['ALL', 'INFO', 'WARN', 'ERROR', 'SUCCESS'];

  return (
    <div className="flex flex-col h-full">
      {/* Terminal header */}
      <div
        className="flex items-center gap-2 px-3 py-2 flex-shrink-0 border-b border-white/8"
        style={{ background: 'rgba(10,10,20,0.8)' }}
      >
        <ScrollText size={13} className="text-slate-400" />
        <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Live Log Feed</span>
        <span className="ml-1 text-xs text-slate-600">({filtered.length})</span>

        {/* Level filters */}
        <div className="flex items-center gap-1 ml-auto">
          {levels.map((lvl) => (
            <button
              key={lvl}
              onClick={() => setFilter(lvl)}
              className={`px-2 py-0.5 rounded text-xs font-semibold transition-all ${
                filter === lvl
                  ? lvl === 'ALL'
                    ? 'bg-slate-600 text-white'
                    : `${LOG_LEVEL_STYLES[lvl as LogLevel].bg} ${LOG_LEVEL_STYLES[lvl as LogLevel].text}`
                  : 'text-slate-600 hover:text-slate-400'
              }`}
            >
              {lvl}
            </button>
          ))}
        </div>

        {/* Auto-scroll toggle */}
        <button
          onClick={() => setAutoScroll((a) => !a)}
          title={autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
          className={`p-1 rounded transition-colors ${
            autoScroll ? 'text-emerald-400' : 'text-slate-600 hover:text-slate-400'
          }`}
        >
          <Activity size={13} />
        </button>
      </div>

      {/* Log lines */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto font-mono text-xs leading-relaxed"
        style={{ background: 'rgba(6,6,14,0.95)' }}
      >
        <div className="p-2 space-y-0.5">
          <AnimatePresence initial={false}>
            {filtered.map((log) => {
              const ls = LOG_LEVEL_STYLES[log.level];
              return (
                <motion.div
                  key={log.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.15 }}
                  className={`flex items-start gap-2 px-2 py-1 rounded ${ls.bg} group`}
                >
                  {/* Level badge */}
                  <span className={`text-[10px] font-bold uppercase tracking-widest flex-shrink-0 mt-px w-14 ${ls.text}`}>
                    [{log.level}]
                  </span>
                  {/* Timestamp */}
                  <span className="text-slate-600 flex-shrink-0 mt-px">{log.timestamp}</span>
                  {/* Source */}
                  {log.source && (
                    <span className="text-slate-500 flex-shrink-0 mt-px">
                      [{log.source}]
                    </span>
                  )}
                  {/* Message */}
                  <span className="text-slate-300 break-all">{log.message}</span>
                </motion.div>
              );
            })}
          </AnimatePresence>
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}

// =========================================================================
// DISCOVERY JOB MODAL
// =========================================================================

const INDUSTRIES = [
  'Restaurant', 'Retail', 'Healthcare', 'Hospitality', 'Automotive',
  'Real Estate', 'Education', 'Fitness', 'Beauty', 'Legal',
  'Financial', 'Technology', 'Construction', 'Other',
];

const COUNTRIES = ['United States', 'United Kingdom', 'Canada', 'Germany', 'France', 'Japan', 'Australia'];

const DATA_SOURCES = ['DuckDuckGo', 'Nominatim', 'SerpAPI'];

interface DiscoveryModalProps {
  onClose: () => void;
  onStart: (data: DiscoveryFormData) => void;
}

interface DiscoveryFormData {
  name: string;
  industry: string;
  country: string;
  city: string;
  sources: string[];
  maxResults: number;
}

interface DiscoveryFormErrors {
  name?: string;
  city?: string;
  sources?: string;
}

function DiscoveryModal({ onClose, onStart }: DiscoveryModalProps) {
  const [form, setForm] = useState<DiscoveryFormData>({
    name: '',
    industry: 'Restaurant',
    country: 'United States',
    city: '',
    sources: ['DuckDuckGo', 'Nominatim'],
    maxResults: 1000,
  });
  const [errors, setErrors] = useState<DiscoveryFormErrors>({});

  const toggleSource = (src: string) => {
    setForm((f) => ({
      ...f,
      sources: f.sources.includes(src)
        ? f.sources.filter((s) => s !== src)
        : [...f.sources, src],
    }));
  };

  const validate = () => {
    const e: DiscoveryFormErrors = {};
    if (!form.name.trim()) e.name = 'Job name is required';
    if (!form.city.trim()) e.city = 'City is required';
    if (form.sources.length === 0) e.sources = 'At least one source required';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = () => {
    if (!validate()) return;
    onStart(form);
    onClose();
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.92, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.92, opacity: 0, y: 20 }}
        transition={{ duration: 0.25 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg rounded-2xl overflow-hidden"
        style={{
          background: 'rgba(14,14,32,0.98)',
          border: '1px solid rgba(255,255,255,0.09)',
          boxShadow: '0 32px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(99,102,241,0.15)',
        }}
      >
        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/8">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 flex items-center justify-center border border-indigo-400/20">
              <Search size={15} className="text-indigo-400" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">New Discovery Job</h2>
              <p className="text-xs text-slate-500">Configure and launch a business discovery run</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-500 hover:text-white hover:bg-white/8 rounded-lg transition-all"
          >
            <X size={16} />
          </button>
        </div>

        {/* Form body */}
        <div className="px-6 py-5 space-y-4">
          {/* Job Name */}
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
              Job Name
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Restaurants NYC Q4"
              className="input-dark"
            />
            {errors.name && <p className="text-red-400 text-xs mt-1">{errors.name}</p>}
          </div>

          {/* Industry + Country row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
                Industry
              </label>
              <select
                value={form.industry}
                onChange={(e) => setForm((f) => ({ ...f, industry: e.target.value }))}
                className="input-dark"
                style={{ background: 'var(--bg-card)' }}
              >
                {INDUSTRIES.map((ind) => (
                  <option key={ind} value={ind}>{ind}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
                Country
              </label>
              <select
                value={form.country}
                onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))}
                className="input-dark"
                style={{ background: 'var(--bg-card)' }}
              >
                {COUNTRIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          {/* City */}
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
              City
            </label>
            <div className="relative">
              <MapPin size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={form.city}
                onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
                placeholder="e.g. New York"
                className="input-dark pl-8"
              />
            </div>
            {errors.city && <p className="text-red-400 text-xs mt-1">{errors.city}</p>}
          </div>

          {/* Data Sources */}
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wider">
              Data Sources
            </label>
            <div className="flex flex-wrap gap-2">
              {DATA_SOURCES.map((src) => {
                const checked = form.sources.includes(src);
                return (
                  <button
                    key={src}
                    type="button"
                    onClick={() => toggleSource(src)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                      checked
                        ? 'bg-indigo-500/20 text-indigo-300 border-indigo-400/40'
                        : 'bg-white/5 text-slate-400 border-white/10 hover:border-white/20'
                    }`}
                  >
                    <Database size={11} />
                    {src}
                    {checked && (
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 ml-0.5" />
                    )}
                  </button>
                );
              })}
            </div>
            {errors.sources && (
              <p className="text-red-400 text-xs mt-1">{errors.sources}</p>
            )}
          </div>

          {/* Max Results slider */}
          <div>
            <label className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wider">
              <span>Max Results</span>
              <span className="text-indigo-400 font-bold text-sm normal-case">
                {form.maxResults.toLocaleString()}
              </span>
            </label>
            <input
              type="range"
              min={100}
              max={10000}
              step={100}
              value={form.maxResults}
              onChange={(e) => setForm((f) => ({ ...f, maxResults: Number(e.target.value) }))}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
              style={{
                background: `linear-gradient(to right, #6366F1 0%, #6366F1 ${((form.maxResults - 100) / 9900) * 100}%, rgba(255,255,255,0.1) ${((form.maxResults - 100) / 9900) * 100}%, rgba(255,255,255,0.1) 100%)`,
              }}
            />
            <div className="flex justify-between text-xs text-slate-600 mt-1">
              <span>100</span>
              <span>10,000</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/8">
          <button onClick={onClose} className="btn-ghost px-4 py-2 text-sm">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="btn-primary px-5 py-2 text-sm flex items-center gap-2"
          >
            <Play size={14} />
            Start Job
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// =========================================================================
// BULK AUDIT MODAL
// =========================================================================

interface BulkAuditModalProps {
  onClose: () => void;
}

function BulkAuditModal({ onClose }: BulkAuditModalProps) {
  const [filter, setFilter] = useState('');
  const [limit, setLimit] = useState(50);
  const [priority, setPriority] = useState<'high' | 'medium' | 'low'>('high');

  const handleLaunch = () => {
    onClose();
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.92, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.92, opacity: 0, y: 20 }}
        transition={{ duration: 0.25 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-2xl overflow-hidden"
        style={{
          background: 'rgba(14,14,32,0.98)',
          border: '1px solid rgba(255,255,255,0.09)',
          boxShadow: '0 32px 64px rgba(0,0,0,0.6)',
        }}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/8">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center border border-purple-400/20">
              <SlidersHorizontal size={15} className="text-purple-400" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Bulk Audit</h2>
              <p className="text-xs text-slate-500">Queue multiple businesses for audit</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-500 hover:text-white hover:bg-white/8 rounded-lg transition-all"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
              Filter (industry / city)
            </label>
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="e.g. restaurant, Chicago"
              className="input-dark"
            />
          </div>

          <div>
            <label className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wider">
              <span>Business Limit</span>
              <span className="text-purple-400 font-bold text-sm normal-case">{limit}</span>
            </label>
            <input
              type="range"
              min={10}
              max={500}
              step={10}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
              style={{
                background: `linear-gradient(to right, #8B5CF6 0%, #8B5CF6 ${((limit - 10) / 490) * 100}%, rgba(255,255,255,0.1) ${((limit - 10) / 490) * 100}%, rgba(255,255,255,0.1) 100%)`,
              }}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wider">
              Priority
            </label>
            <div className="flex gap-2">
              {(['high', 'medium', 'low'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPriority(p)}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-semibold border capitalize transition-all ${
                    priority === p
                      ? p === 'high'
                        ? 'bg-red-500/20 text-red-300 border-red-400/40'
                        : p === 'medium'
                        ? 'bg-yellow-500/20 text-yellow-300 border-yellow-400/40'
                        : 'bg-slate-500/20 text-slate-300 border-slate-400/40'
                      : 'bg-white/5 text-slate-500 border-white/10 hover:border-white/20'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/8">
          <button onClick={onClose} className="btn-ghost px-4 py-2 text-sm">
            Cancel
          </button>
          <button
            onClick={handleLaunch}
            className="flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-xl transition-all"
            style={{
              background: 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)',
              color: 'white',
              boxShadow: '0 4px 16px rgba(139,92,246,0.35)',
            }}
          >
            <Zap size={14} />
            Launch Audit
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// =========================================================================
// MAIN PAGE
// =========================================================================

export default function CommandCenterPage() {
  // WebSocket (live data when available)
  const { isConnected, status: wsStatus } = useWebSocket();
  const systemStoreStats = useSystemStore((s) => s.systemStats);

  // Local state
  const [jobs, setJobs] = useState<ActiveJob[]>(generateInitialJobs);
  const [logs, setLogs] = useState<LogEntry[]>(generateInitialLogs);
  const [metrics, setMetrics] = useState<LiveMetrics>(generateInitialMetrics);
  const [sysStats, setSysStats] = useState<SystemStats>(generateInitialStats);

  // Modals
  const [showDiscoveryModal, setShowDiscoveryModal] = useState(false);
  const [showBulkAuditModal, setShowBulkAuditModal] = useState(false);

  // Sync system store stats if WS provides them
  useEffect(() => {
    if (isConnected && systemStoreStats) {
      setSysStats({
        cpu: systemStoreStats.cpuUsage,
        memory: systemStoreStats.memoryUsage,
        queue: systemStoreStats.queuedJobs,
        workers: systemStoreStats.activeWorkers,
        msgPerSec: systemStoreStats.requestsPerMinute / 60,
      });
    }
  }, [isConnected, systemStoreStats]);

  // Mock tick — updates every 2s (log) and 5s (metrics / stats)
  const tickRef = useRef(0);
  useEffect(() => {
    const interval = setInterval(() => {
      tickRef.current += 1;

      // New log every tick
      setLogs((prev) => {
        const next = [...prev, generateRandomLog()];
        return next.slice(-200); // max 200 lines
      });

      // Update job progress every 2 ticks (4s)
      if (tickRef.current % 2 === 0) {
        setJobs((prev) =>
          prev.map((job) => {
            if (job.status !== 'running') return job;
            const newProgress = Math.min(100, job.progress + randBetween(0, 3));
            const newDiscovered = Math.min(
              job.total,
              job.discovered + randBetween(0, 25)
            );
            const secsLeft = Math.floor(
              (job.total - newDiscovered) / (Math.random() * 5 + 2)
            );
            const mins = Math.floor(secsLeft / 60);
            return {
              ...job,
              progress: newProgress,
              discovered: newDiscovered,
              eta: mins > 0 ? `${mins}m left` : '<1m left',
              status: newProgress >= 100 ? 'queued' : job.status,
            };
          })
        );
      }

      // Metrics every 5 ticks (10s when using 2s interval)
      if (tickRef.current % 5 === 0) {
        setSysStats({
          cpu: randBetween(28, 72),
          memory: randBetween(40, 78),
          queue: randBetween(80, 600),
          workers: randBetween(3, 8),
          msgPerSec: randBetween(5, 45),
        });

        const addPoint = (arr: MetricPoint[], gen: () => number): MetricPoint[] => {
          const next = [...arr, { t: fmtTime(), v: gen() }];
          return next.slice(-30);
        };

        setMetrics((prev) => ({
          discoveryRate: addPoint(prev.discoveryRate, () => randBetween(8, 42)),
          auditRate: addPoint(prev.auditRate, () => randBetween(1, 12)),
          errorRate: addPoint(prev.errorRate, () => parseFloat((Math.random() * 4).toFixed(1))),
          queueDepth: addPoint(prev.queueDepth, () => randBetween(80, 620)),
        }));
      }
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  // Job controls
  const handleTogglePause = useCallback((id: string) => {
    setJobs((prev) =>
      prev.map((j) =>
        j.id === id
          ? { ...j, status: j.status === 'paused' ? 'running' : 'paused' }
          : j
      )
    );
    const job = jobs.find((j) => j.id === id);
    if (job) {
      setLogs((prev) => [
        ...prev,
        {
          id: `log-${Date.now()}`,
          level: 'INFO' as LogLevel,
          message: `Job "${job.name}" ${job.status === 'paused' ? 'resumed' : 'paused'} by user`,
          source: 'operator',
          timestamp: fmtTime(),
        },
      ].slice(-200));
    }
  }, [jobs]);

  const handleStopJob = useCallback((id: string) => {
    const job = jobs.find((j) => j.id === id);
    setJobs((prev) => prev.filter((j) => j.id !== id));
    if (job) {
      setLogs((prev) => [
        ...prev,
        {
          id: `log-${Date.now()}`,
          level: 'WARN' as LogLevel,
          message: `Job "${job.name}" stopped by user`,
          source: 'operator',
          timestamp: fmtTime(),
        },
      ].slice(-200));
    }
  }, [jobs]);

  const handlePauseAll = useCallback(() => {
    setJobs((prev) =>
      prev.map((j) => (j.status === 'running' ? { ...j, status: 'paused' } : j))
    );
    setLogs((prev) => [
      ...prev,
      {
        id: `log-${Date.now()}`,
        level: 'WARN' as LogLevel,
        message: 'All running jobs paused by operator',
        source: 'operator',
        timestamp: fmtTime(),
      },
    ].slice(-200));
  }, []);

  const handleResumeAll = useCallback(() => {
    setJobs((prev) =>
      prev.map((j) => (j.status === 'paused' ? { ...j, status: 'running' } : j))
    );
    setLogs((prev) => [
      ...prev,
      {
        id: `log-${Date.now()}`,
        level: 'SUCCESS' as LogLevel,
        message: 'All paused jobs resumed by operator',
        source: 'operator',
        timestamp: fmtTime(),
      },
    ].slice(-200));
  }, []);

  const handleClearCompleted = useCallback(() => {
    setJobs((prev) => prev.filter((j) => j.status !== 'queued' && j.progress < 100));
  }, []);

  const handleStartDiscovery = useCallback((data: DiscoveryFormData) => {
    const newJob: ActiveJob = {
      id: `job-${Date.now()}`,
      name: data.name,
      provider: data.sources[0] || 'DuckDuckGo',
      progress: 0,
      status: 'running',
      eta: 'calculating...',
      discovered: 0,
      total: data.maxResults,
      location: `${data.city}, ${data.country}`,
      startedAt: new Date().toISOString(),
    };
    setJobs((prev) => [newJob, ...prev]);
    setLogs((prev) => [
      ...prev,
      {
        id: `log-${Date.now()}`,
        level: 'SUCCESS' as LogLevel,
        message: `Discovery job "${data.name}" started — target: ${data.maxResults.toLocaleString()} businesses`,
        source: 'discovery',
        timestamp: fmtTime(),
      },
    ].slice(-200));
  }, []);

  // Derived
  const lastDiscovery = metrics.discoveryRate.at(-1)?.v ?? 0;
  const prevDiscovery = metrics.discoveryRate.at(-2)?.v ?? 0;
  const lastAudit = metrics.auditRate.at(-1)?.v ?? 0;
  const prevAudit = metrics.auditRate.at(-2)?.v ?? 0;
  const lastError = metrics.errorRate.at(-1)?.v ?? 0;
  const prevError = metrics.errorRate.at(-2)?.v ?? 0;
  const lastQueue = metrics.queueDepth.at(-1)?.v ?? 0;
  const prevQueue = metrics.queueDepth.at(-2)?.v ?? 0;

  const cpuColor = sysStats.cpu > 80 ? 'text-red-400' : sysStats.cpu > 60 ? 'text-yellow-400' : 'text-emerald-400';
  const memColor = sysStats.memory > 80 ? 'text-red-400' : sysStats.memory > 60 ? 'text-yellow-400' : 'text-emerald-400';

  return (
    <>
      <div
        className="min-h-full p-6 space-y-5 bg-grid-sm"
        style={{ background: 'linear-gradient(180deg, #0A0A14 0%, #080810 100%)' }}
      >

        {/* ================================================================
            TOP STATUS BAR
        ================================================================ */}
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <GlassCard padding="none" glow glowColor="rgba(16,185,129,0.1)">
            <div className="flex flex-wrap items-center gap-4 px-5 py-3">
              {/* System Online */}
              <div className="flex items-center gap-2.5">
                <PulsingDot color={isConnected ? 'bg-emerald-400' : 'bg-yellow-400'} />
                <span className="text-sm font-bold tracking-widest uppercase"
                  style={{
                    color: isConnected ? '#34D399' : '#FBBF24',
                    textShadow: isConnected
                      ? '0 0 12px rgba(52,211,153,0.6)'
                      : '0 0 12px rgba(251,191,36,0.6)',
                  }}
                >
                  {isConnected ? 'SYSTEM ONLINE' : 'MOCK MODE'}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-semibold border ${
                    wsStatus === 'connected'
                      ? 'bg-emerald-400/10 text-emerald-400 border-emerald-400/20'
                      : wsStatus === 'connecting'
                      ? 'bg-blue-400/10 text-blue-400 border-blue-400/20'
                      : 'bg-yellow-400/10 text-yellow-400 border-yellow-400/20'
                  }`}
                >
                  WS: {wsStatus.toUpperCase()}
                </span>
              </div>

              <div className="h-4 w-px bg-white/10 hidden sm:block" />

              {/* CPU */}
              <div className="flex items-center gap-2">
                <Cpu size={14} className="text-slate-500" />
                <span className="text-xs text-slate-500">CPU</span>
                <span className={`text-sm font-bold ${cpuColor}`}>{sysStats.cpu}%</span>
              </div>

              {/* Memory */}
              <div className="flex items-center gap-2">
                <MemoryStick size={14} className="text-slate-500" />
                <span className="text-xs text-slate-500">MEM</span>
                <span className={`text-sm font-bold ${memColor}`}>{sysStats.memory}%</span>
              </div>

              {/* Queue */}
              <div className="flex items-center gap-2">
                <Layers size={14} className="text-slate-500" />
                <span className="text-xs text-slate-500">Queue</span>
                <span className="text-sm font-bold text-white">{sysStats.queue.toLocaleString()}</span>
              </div>

              <div className="h-4 w-px bg-white/10 hidden sm:block" />

              {/* Workers */}
              <div className="flex items-center gap-2">
                <Users size={14} className="text-slate-500" />
                <span className="text-xs text-slate-500">Workers</span>
                <span className="text-sm font-bold text-indigo-400">{sysStats.workers}</span>
              </div>

              {/* Msg/sec */}
              <div className="flex items-center gap-2">
                <Zap size={14} className="text-slate-500" />
                <span className="text-xs text-slate-500">Msg/s</span>
                <span className="text-sm font-bold text-purple-400">{sysStats.msgPerSec.toFixed(1)}</span>
              </div>

              {/* Active jobs */}
              <div className="flex items-center gap-2">
                <Activity size={14} className="text-slate-500" />
                <span className="text-xs text-slate-500">Active</span>
                <span className="text-sm font-bold text-blue-400">
                  {jobs.filter((j) => j.status === 'running').length} jobs
                </span>
              </div>

              {/* Timestamp */}
              <div className="ml-auto text-xs text-slate-600 font-mono">
                {new Date().toUTCString().replace(' GMT', ' UTC')}
              </div>
            </div>
          </GlassCard>
        </motion.div>

        {/* ================================================================
            QUICK ACTIONS BAR
        ================================================================ */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.05 }}
          className="flex flex-wrap items-center gap-2"
        >
          <button
            onClick={() => setShowDiscoveryModal(true)}
            className="btn-primary flex items-center gap-2 px-4 py-2 text-sm"
          >
            <Plus size={14} />
            New Discovery Job
          </button>
          <button
            onClick={() => setShowBulkAuditModal(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-xl border transition-all"
            style={{
              background: 'rgba(139,92,246,0.15)',
              color: '#C4B5FD',
              borderColor: 'rgba(139,92,246,0.3)',
            }}
          >
            <Zap size={14} />
            Bulk Audit
          </button>

          <div className="h-6 w-px bg-white/10" />

          <button
            onClick={handlePauseAll}
            className="btn-ghost flex items-center gap-2 px-3 py-2 text-sm"
          >
            <Pause size={13} />
            Pause All
          </button>
          <button
            onClick={handleResumeAll}
            className="btn-ghost flex items-center gap-2 px-3 py-2 text-sm"
          >
            <Play size={13} />
            Resume All
          </button>
          <button
            onClick={handleClearCompleted}
            className="btn-ghost flex items-center gap-2 px-3 py-2 text-sm text-slate-500 hover:text-red-400"
          >
            <Trash2 size={13} />
            Clear Completed
          </button>

          <div className="ml-auto flex items-center gap-2">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/8 text-xs text-slate-500">
              <RefreshCw size={11} className={isConnected ? 'text-emerald-400' : 'animate-spin text-yellow-400'} />
              {isConnected ? 'Live' : 'Polling 5s'}
            </div>
          </div>
        </motion.div>

        {/* ================================================================
            MAIN TWO-COLUMN: JOBS + LOG FEED
        ================================================================ */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
          className="grid grid-cols-1 xl:grid-cols-5 gap-5"
          style={{ minHeight: '420px' }}
        >
          {/* LEFT: Active Jobs — 60% */}
          <div className="xl:col-span-3 flex flex-col gap-3">
            {/* Jobs header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity size={15} className="text-blue-400" />
                <span className="text-sm font-bold text-white">Active Jobs</span>
                <span className="badge badge-primary text-xs">
                  {jobs.filter((j) => j.status === 'running').length} running
                </span>
                {jobs.some((j) => j.status === 'paused') && (
                  <span className="badge badge-warning text-xs">
                    {jobs.filter((j) => j.status === 'paused').length} paused
                  </span>
                )}
                {jobs.some((j) => j.status === 'failed') && (
                  <span className="badge badge-error text-xs">
                    {jobs.filter((j) => j.status === 'failed').length} failed
                  </span>
                )}
              </div>
              <button
                onClick={() => setShowDiscoveryModal(true)}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-400 transition-colors"
              >
                <Plus size={12} />
                Add Job
              </button>
            </div>

            {/* Job cards */}
            <div className="space-y-3 flex-1">
              <AnimatePresence mode="popLayout">
                {jobs.length === 0 ? (
                  <motion.div
                    key="empty"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    <GlassCard padding="lg" className="flex flex-col items-center justify-center py-16 text-center">
                      <div
                        className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
                        style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.15)' }}
                      >
                        <Activity size={24} className="text-slate-500" />
                      </div>
                      <p className="text-slate-400 font-semibold">No active jobs</p>
                      <p className="text-slate-600 text-sm mt-1">Launch a discovery job to get started</p>
                      <button
                        onClick={() => setShowDiscoveryModal(true)}
                        className="btn-primary mt-4 px-5 py-2 text-sm flex items-center gap-2"
                      >
                        <Plus size={14} />
                        New Discovery Job
                      </button>
                    </GlassCard>
                  </motion.div>
                ) : (
                  jobs.map((job) => (
                    <JobCard
                      key={job.id}
                      job={job}
                      onTogglePause={handleTogglePause}
                      onStop={handleStopJob}
                    />
                  ))
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* RIGHT: Log Feed — 40% */}
          <div className="xl:col-span-2 min-h-[420px]">
            <GlassCard
              padding="none"
              className="overflow-hidden h-full"
            >
              <div className="flex flex-col h-full" style={{ minHeight: '420px' }}>
                <LogFeed logs={logs} />
              </div>
            </GlassCard>
          </div>
        </motion.div>

        {/* ================================================================
            METRICS ROW — 4 MINI CHARTS
        ================================================================ */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2 }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Globe size={14} className="text-purple-400" />
            <span className="text-sm font-bold text-white">Live Metrics</span>
            <span className="text-xs text-slate-600">— last 30 data points</span>
          </div>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <MiniChart
              data={metrics.discoveryRate}
              label="Discovery Rate"
              value={String(lastDiscovery)}
              unit="biz/min"
              color="#6366F1"
              delta={lastDiscovery - prevDiscovery}
            />
            <MiniChart
              data={metrics.auditRate}
              label="Audit Rate"
              value={String(lastAudit)}
              unit="audits/min"
              color="#8B5CF6"
              delta={lastAudit - prevAudit}
            />
            <MiniChart
              data={metrics.errorRate}
              label="Error Rate"
              value={lastError.toFixed(1)}
              unit="%"
              color="#EF4444"
              delta={lastError - prevError}
            />
            <MiniChart
              data={metrics.queueDepth}
              label="Queue Depth"
              value={String(lastQueue)}
              unit="items"
              color="#F59E0B"
              delta={lastQueue - prevQueue}
            />
          </div>
        </motion.div>

      </div>

      {/* ================================================================
          MODALS
      ================================================================ */}
      <AnimatePresence>
        {showDiscoveryModal && (
          <DiscoveryModal
            key="discovery-modal"
            onClose={() => setShowDiscoveryModal(false)}
            onStart={handleStartDiscovery}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showBulkAuditModal && (
          <BulkAuditModal
            key="bulk-audit-modal"
            onClose={() => setShowBulkAuditModal(false)}
          />
        )}
      </AnimatePresence>
    </>
  );
}
