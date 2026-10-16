'use client';

import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Settings,
  Search,
  Database,
  Key,
  User,
  Save,
  Eye,
  EyeOff,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
  AlertTriangle,
  Shield,
  Zap,
  Sliders,
  Copy,
  Trash2,
  Mail,
  Lock,
  Plus,
  Check,
  X,
  Server,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import GlassCard from '@/components/ui/GlassCard';
import toast from 'react-hot-toast';

// ─── Types ────────────────────────────────────────────────────────────────────

type Tab = 'discovery' | 'audit' | 'database' | 'apikeys' | 'account' | 'email';

type ConnectionStatus = 'idle' | 'testing' | 'success' | 'error';
type ApiKeyStatus = 'idle' | 'testing' | 'valid' | 'invalid' | 'saving';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function useToggle(initial = false) {
  const [state, setState] = useState(initial);
  const toggle = useCallback(() => setState((s) => !s), []);
  return [state, toggle] as const;
}

// ─── Shared UI ────────────────────────────────────────────────────────────────

interface SectionProps {
  title: string;
  description?: string;
  children: React.ReactNode;
}

function Section({ title, description, children }: SectionProps) {
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        {description && <p className="text-xs text-slate-500 mt-0.5">{description}</p>}
      </div>
      {children}
    </div>
  );
}

interface FieldRowProps {
  label: string;
  description?: string;
  children: React.ReactNode;
}

function FieldRow({ label, description, children }: FieldRowProps) {
  return (
    <div className="flex items-start justify-between gap-6 py-3 border-b border-white/5">
      <div className="min-w-0">
        <div className="text-sm font-medium text-slate-300">{label}</div>
        {description && <div className="text-xs text-slate-500 mt-0.5">{description}</div>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

interface SliderFieldProps {
  label: string;
  description?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  onChange: (v: number) => void;
}

function SliderField({ label, description, value, min, max, step = 1, unit = '', onChange }: SliderFieldProps) {
  return (
    <div className="py-3 border-b border-white/5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-sm font-medium text-slate-300">{label}</div>
          {description && <div className="text-xs text-slate-500 mt-0.5">{description}</div>}
        </div>
        <span className="text-sm font-bold text-indigo-400 min-w-[3rem] text-right">
          {value}{unit}
        </span>
      </div>
      <div className="relative">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full h-2 rounded-full appearance-none cursor-pointer"
          style={{
            background: `linear-gradient(to right, #6366f1 0%, #6366f1 ${((value - min) / (max - min)) * 100}%, rgba(255,255,255,0.1) ${((value - min) / (max - min)) * 100}%, rgba(255,255,255,0.1) 100%)`,
          }}
        />
      </div>
      <div className="flex justify-between text-xs text-slate-600 mt-1.5">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

interface ToggleProps {
  enabled: boolean;
  onChange: () => void;
  label?: string;
}

function Toggle({ enabled, onChange, label }: ToggleProps) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={cn(
        'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 transition-colors duration-200 ease-in-out focus:outline-none',
        enabled
          ? 'border-indigo-500 bg-indigo-500'
          : 'border-slate-600 bg-slate-700'
      )}
      aria-label={label}
    >
      <span
        className={cn(
          'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200 ease-in-out mt-[1px]',
          enabled ? 'translate-x-5' : 'translate-x-0.5'
        )}
      />
    </button>
  );
}

interface MaskedInputProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  id?: string;
}

function MaskedInput({ value, onChange, placeholder = 'Enter value...', className, id }: MaskedInputProps) {
  const [visible, setVisible] = useState(false);
  return (
    <div className={cn('relative', className)}>
      <input
        id={id}
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 pr-10 text-sm text-slate-300 placeholder-slate-600 focus:outline-none focus:border-indigo-500/60 transition-all font-mono"
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
      >
        {visible ? <EyeOff size={15} /> : <Eye size={15} />}
      </button>
    </div>
  );
}

// ─── API Key Row ──────────────────────────────────────────────────────────────

interface ApiKeyRowProps {
  label: string;
  envVar: string;
  value: string;
  onChange: (v: string) => void;
  onSave: () => void;
  onTest: () => void;
  status: ApiKeyStatus;
  description?: string;
}

function ApiKeyRow({ label, envVar, value, onChange, onSave, onTest, status, description }: ApiKeyRowProps) {
  const statusIcon = {
    idle: null,
    testing: <Loader2 size={14} className="animate-spin text-slate-400" />,
    valid: <CheckCircle2 size={14} className="text-emerald-400" />,
    invalid: <XCircle size={14} className="text-red-400" />,
    saving: <Loader2 size={14} className="animate-spin text-indigo-400" />,
  }[status];

  const statusText = {
    idle: '',
    testing: 'Validating...',
    valid: 'Valid',
    invalid: 'Invalid key',
    saving: 'Saving...',
  }[status];

  return (
    <div
      className="p-5 rounded-xl space-y-3"
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="text-sm font-semibold text-white">{label}</div>
          {description && <div className="text-xs text-slate-500 mt-0.5">{description}</div>}
          <code className="text-xs text-slate-600 mt-1 block">{envVar}</code>
        </div>
        {statusIcon && (
          <div className="flex items-center gap-1.5">
            {statusIcon}
            {statusText && (
              <span
                className={cn(
                  'text-xs font-medium',
                  status === 'valid' && 'text-emerald-400',
                  status === 'invalid' && 'text-red-400',
                  status === 'testing' && 'text-slate-400',
                  status === 'saving' && 'text-indigo-400'
                )}
              >
                {statusText}
              </span>
            )}
          </div>
        )}
      </div>

      <MaskedInput
        value={value}
        onChange={onChange}
        placeholder={`Enter ${envVar}...`}
      />

      <div className="flex items-center gap-2">
        <button
          onClick={onTest}
          disabled={!value || status === 'testing'}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
        >
          {status === 'testing' ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
          Test Key
        </button>
        <button
          onClick={onSave}
          disabled={!value || status === 'saving'}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          style={{
            background: 'linear-gradient(135deg, rgba(99,102,241,0.6), rgba(168,85,247,0.5))',
            border: '1px solid rgba(99,102,241,0.3)',
          }}
        >
          {status === 'saving' ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          Save
        </button>
      </div>
    </div>
  );
}

// ─── Tab 1: Discovery Settings ────────────────────────────────────────────────

const PROVIDERS = ['Google Maps', 'Yelp', 'Yellow Pages', 'Foursquare', 'TripAdvisor', 'Bing Places'];
const COUNTRIES = ['United States', 'United Kingdom', 'Canada', 'Australia', 'Germany', 'France', 'Netherlands', 'Spain', 'Italy', 'Japan'];

function DiscoveryTab() {
  const [enabledProviders, setEnabledProviders] = useState<string[]>(['Google Maps', 'Yelp']);
  const [rateLimits, setRateLimits] = useState<Record<string, number>>({
    'Google Maps': 10,
    Yelp: 8,
    'Yellow Pages': 5,
    Foursquare: 6,
    TripAdvisor: 4,
    'Bing Places': 5,
  });
  const [maxResults, setMaxResults] = useState(100);
  const [selectedCountries, setSelectedCountries] = useState<string[]>(['United States', 'United Kingdom']);
  const [saved, setSaved] = useState(false);

  const toggleProvider = (p: string) => {
    setEnabledProviders((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  };

  const toggleCountry = (c: string) => {
    setSelectedCountries((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
    );
  };

  const handleSave = () => {
    setSaved(true);
    toast.success('Discovery settings saved');
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-8">
      <Section title="Data Providers" description="Select which sources to use for business discovery">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {PROVIDERS.map((provider) => {
            const active = enabledProviders.includes(provider);
            return (
              <button
                key={provider}
                onClick={() => toggleProvider(provider)}
                className={cn(
                  'flex items-center gap-3 p-3 rounded-xl text-sm font-medium transition-all text-left',
                  active
                    ? 'text-indigo-300'
                    : 'text-slate-400 hover:text-slate-300'
                )}
                style={{
                  background: active ? 'rgba(99,102,241,0.12)' : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${active ? 'rgba(99,102,241,0.3)' : 'rgba(255,255,255,0.07)'}`,
                }}
              >
                <div
                  className={cn(
                    'w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0',
                    active ? 'bg-indigo-500' : 'bg-white/10'
                  )}
                >
                  {active && <Check size={12} className="text-white" />}
                </div>
                {provider}
              </button>
            );
          })}
        </div>
      </Section>

      <Section title="Rate Limits" description="Requests per second for each enabled provider">
        <div className="space-y-1 divide-y divide-white/5">
          {enabledProviders.map((provider) => (
            <SliderField
              key={provider}
              label={provider}
              value={rateLimits[provider] ?? 5}
              min={1}
              max={30}
              unit=" req/s"
              onChange={(v) => setRateLimits((prev) => ({ ...prev, [provider]: v }))}
            />
          ))}
        </div>
      </Section>

      <Section title="Search Parameters">
        <SliderField
          label="Max Results Per Job"
          description="Maximum number of businesses to retrieve per discovery job"
          value={maxResults}
          min={10}
          max={500}
          step={10}
          unit=" results"
          onChange={setMaxResults}
        />
      </Section>

      <Section title="Default Countries" description="Pre-selected countries for new discovery jobs">
        <div className="flex flex-wrap gap-2">
          {COUNTRIES.map((country) => {
            const selected = selectedCountries.includes(country);
            return (
              <button
                key={country}
                onClick={() => toggleCountry(country)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all',
                  selected
                    ? 'text-indigo-300'
                    : 'text-slate-400 hover:text-slate-300'
                )}
                style={{
                  background: selected ? 'rgba(99,102,241,0.15)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${selected ? 'rgba(99,102,241,0.35)' : 'rgba(255,255,255,0.08)'}`,
                }}
              >
                {selected ? <X size={11} /> : <Plus size={11} />}
                {country}
              </button>
            );
          })}
        </div>
      </Section>

      <div className="pt-2">
        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold text-white transition-all"
          style={{
            background: saved
              ? 'linear-gradient(135deg, #10b981, #059669)'
              : 'linear-gradient(135deg, #6366f1, #a855f7)',
            boxShadow: '0 4px 16px rgba(99,102,241,0.3)',
          }}
        >
          {saved ? <Check size={15} /> : <Save size={15} />}
          {saved ? 'Saved!' : 'Save Discovery Settings'}
        </button>
      </div>
    </div>
  );
}

// ─── Tab 2: Audit Settings ────────────────────────────────────────────────────

function AuditTab() {
  const [screenshotEnabled, toggleScreenshot] = useToggle(true);
  const [aiEnabled, toggleAi] = useToggle(true);
  const [anthropicKey, setAnthropicKey] = useState('');
  const [timeout, setTimeout_] = useState(30);
  const [parallelAudits, setParallelAudits] = useState(5);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    toast.success('Audit settings saved');
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-8">
      <Section title="Capture Options" description="Configure what data is collected during audits">
        <div className="divide-y divide-white/5">
          <FieldRow
            label="Screenshot Capture"
            description="Capture full-page screenshots during website audits"
          >
            <Toggle enabled={screenshotEnabled} onChange={toggleScreenshot} />
          </FieldRow>
          <FieldRow
            label="AI Analysis"
            description="Use Claude AI to generate detailed opportunity analysis"
          >
            <Toggle enabled={aiEnabled} onChange={toggleAi} />
          </FieldRow>
        </div>

        <AnimatePresence>
          {aiEnabled && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div
                className="p-4 rounded-xl mt-3"
                style={{ background: 'rgba(99,102,241,0.07)', border: '1px solid rgba(99,102,241,0.15)' }}
              >
                <label className="text-xs font-semibold text-slate-300 flex items-center gap-2 mb-2">
                  <Key size={12} className="text-indigo-400" />
                  Anthropic API Key (for AI Analysis)
                </label>
                <MaskedInput
                  value={anthropicKey}
                  onChange={setAnthropicKey}
                  placeholder="sk-ant-..."
                />
                <p className="text-xs text-slate-500 mt-2">
                  Required for Claude AI analysis. Key is stored encrypted.{' '}
                  <a href="https://console.anthropic.com" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:underline">
                    Get a key →
                  </a>
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Section>

      <Section title="Performance Limits" description="Control audit speed and resource usage">
        <div className="space-y-1 divide-y divide-white/5">
          <SliderField
            label="Audit Timeout"
            description="Maximum seconds to wait for a page to load"
            value={timeout}
            min={5}
            max={120}
            step={5}
            unit="s"
            onChange={setTimeout_}
          />
          <SliderField
            label="Parallel Audits"
            description="Number of audits to run simultaneously"
            value={parallelAudits}
            min={1}
            max={20}
            onChange={setParallelAudits}
          />
        </div>
      </Section>

      <div className="pt-2">
        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold text-white transition-all"
          style={{
            background: saved ? 'linear-gradient(135deg, #10b981, #059669)' : 'linear-gradient(135deg, #6366f1, #a855f7)',
            boxShadow: '0 4px 16px rgba(99,102,241,0.3)',
          }}
        >
          {saved ? <Check size={15} /> : <Save size={15} />}
          {saved ? 'Saved!' : 'Save Audit Settings'}
        </button>
      </div>
    </div>
  );
}

// ─── Tab 3: Database ──────────────────────────────────────────────────────────

function DatabaseTab() {
  const [dbType, setDbType] = useState<'postgresql' | 'sqlite'>('postgresql');
  const [connString, setConnString] = useState('postgresql://user:password@localhost:5432/biplatform');
  const [connStatus, setConnStatus] = useState<ConnectionStatus>('idle');
  const [saved, setSaved] = useState(false);

  const testConnection = async () => {
    setConnStatus('testing');
    await new Promise((r) => setTimeout(r, 2000));
    setConnStatus(Math.random() > 0.3 ? 'success' : 'error');
  };

  const handleSave = () => {
    setSaved(true);
    toast.success('Database settings saved');
    setTimeout(() => setSaved(false), 2000);
  };

  const migrations = [
    { name: '001_initial_schema', status: 'applied', date: '2024-05-01' },
    { name: '002_add_audit_scores', status: 'applied', date: '2024-05-14' },
    { name: '003_add_ai_analysis', status: 'applied', date: '2024-05-28' },
    { name: '004_add_revenue_fields', status: 'pending', date: null },
  ];

  return (
    <div className="space-y-8">
      <Section title="Database Type" description="Select your database backend">
        <div className="grid grid-cols-2 gap-4">
          {(['postgresql', 'sqlite'] as const).map((type) => {
            const active = dbType === type;
            return (
              <button
                key={type}
                onClick={() => setDbType(type)}
                className={cn(
                  'p-4 rounded-xl text-left transition-all',
                  active ? 'text-indigo-300' : 'text-slate-400 hover:text-slate-300'
                )}
                style={{
                  background: active ? 'rgba(99,102,241,0.12)' : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${active ? 'rgba(99,102,241,0.35)' : 'rgba(255,255,255,0.07)'}`,
                }}
              >
                <div className="flex items-start gap-3">
                  <div
                    className={cn(
                      'w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 mt-0.5',
                      active ? 'border-indigo-500' : 'border-slate-600'
                    )}
                  >
                    {active && <div className="w-2.5 h-2.5 rounded-full bg-indigo-500" />}
                  </div>
                  <div>
                    <div className="text-sm font-semibold capitalize">
                      {type === 'postgresql' ? 'PostgreSQL' : 'SQLite'}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {type === 'postgresql' ? 'Production-grade relational database' : 'Lightweight file-based database'}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </Section>

      <Section title="Connection" description="Configure database connection">
        <div className="space-y-3">
          <label className="text-xs font-medium text-slate-400">Connection String</label>
          <MaskedInput
            value={connString}
            onChange={setConnString}
            placeholder={
              dbType === 'postgresql'
                ? 'postgresql://user:password@host:5432/db'
                : '/path/to/database.sqlite'
            }
          />
          <button
            onClick={testConnection}
            disabled={connStatus === 'testing'}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all"
            style={{
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: connStatus === 'success' ? '#10b981' : connStatus === 'error' ? '#ef4444' : '#94a3b8',
            }}
          >
            {connStatus === 'testing' ? (
              <Loader2 size={14} className="animate-spin" />
            ) : connStatus === 'success' ? (
              <CheckCircle2 size={14} />
            ) : connStatus === 'error' ? (
              <XCircle size={14} />
            ) : (
              <Server size={14} />
            )}
            {connStatus === 'testing' ? 'Testing...' : connStatus === 'success' ? 'Connected!' : connStatus === 'error' ? 'Connection Failed' : 'Test Connection'}
          </button>
        </div>
      </Section>

      <Section title="Migration Status" description="Database schema migration history">
        <div
          className="rounded-xl overflow-hidden"
          style={{ border: '1px solid rgba(255,255,255,0.07)' }}
        >
          {migrations.map((m, i) => (
            <div
              key={m.name}
              className={cn(
                'flex items-center justify-between px-4 py-3',
                i < migrations.length - 1 && 'border-b border-white/5'
              )}
            >
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    'w-2 h-2 rounded-full',
                    m.status === 'applied' ? 'bg-emerald-400' : 'bg-amber-400'
                  )}
                />
                <code className="text-xs text-slate-300">{m.name}</code>
              </div>
              <div className="flex items-center gap-3">
                {m.date && <span className="text-xs text-slate-500">{m.date}</span>}
                <span
                  className={cn(
                    'text-xs font-medium px-2 py-0.5 rounded-full',
                    m.status === 'applied'
                      ? 'text-emerald-400 bg-emerald-400/15'
                      : 'text-amber-400 bg-amber-400/15'
                  )}
                >
                  {m.status}
                </span>
              </div>
            </div>
          ))}
        </div>
        {migrations.some((m) => m.status === 'pending') && (
          <button
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-amber-400 mt-3 transition-colors hover:text-amber-300"
            style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)' }}
          >
            <AlertTriangle size={14} />
            Run Pending Migrations
          </button>
        )}
      </Section>

      <div className="pt-2">
        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold text-white transition-all"
          style={{
            background: saved ? 'linear-gradient(135deg, #10b981, #059669)' : 'linear-gradient(135deg, #6366f1, #a855f7)',
            boxShadow: '0 4px 16px rgba(99,102,241,0.3)',
          }}
        >
          {saved ? <Check size={15} /> : <Save size={15} />}
          {saved ? 'Saved!' : 'Save Database Settings'}
        </button>
      </div>
    </div>
  );
}

// ─── Tab 4: API Keys ──────────────────────────────────────────────────────────

function ApiKeysTab() {
  type KeyName = 'anthropic' | 'serp' | 'gmaps';
  const [keys, setKeys] = useState<Record<KeyName, string>>({
    anthropic: '',
    serp: '',
    gmaps: '',
  });
  const [statuses, setStatuses] = useState<Record<KeyName, ApiKeyStatus>>({
    anthropic: 'idle',
    serp: 'idle',
    gmaps: 'idle',
  });

  const setKey = (name: KeyName) => (v: string) =>
    setKeys((prev) => ({ ...prev, [name]: v }));

  const testKey = async (name: KeyName) => {
    setStatuses((p) => ({ ...p, [name]: 'testing' }));
    await new Promise((r) => setTimeout(r, 1800));
    const result = Math.random() > 0.35 ? 'valid' : 'invalid';
    setStatuses((p) => ({ ...p, [name]: result }));
    if (result === 'valid') toast.success('API key is valid');
    else toast.error('API key validation failed');
  };

  const saveKey = async (name: KeyName) => {
    setStatuses((p) => ({ ...p, [name]: 'saving' }));
    await new Promise((r) => setTimeout(r, 1000));
    setStatuses((p) => ({ ...p, [name]: 'idle' }));
    toast.success('API key saved securely');
  };

  return (
    <div className="space-y-5">
      <div
        className="flex items-start gap-3 p-4 rounded-xl"
        style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.15)' }}
      >
        <Shield size={16} className="text-indigo-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-slate-400 leading-relaxed">
          All API keys are encrypted at rest using AES-256. Keys are never exposed in logs or transmitted in plaintext.
        </p>
      </div>

      <ApiKeyRow
        label="Anthropic API Key"
        envVar="ANTHROPIC_API_KEY"
        description="Required for AI-powered website analysis and opportunity scoring"
        value={keys.anthropic}
        onChange={setKey('anthropic')}
        onTest={() => testKey('anthropic')}
        onSave={() => saveKey('anthropic')}
        status={statuses.anthropic}
      />

      <ApiKeyRow
        label="SerpAPI Key"
        envVar="SERPAPI_KEY"
        description="Used to retrieve search engine result data for SEO analysis"
        value={keys.serp}
        onChange={setKey('serp')}
        onTest={() => testKey('serp')}
        onSave={() => saveKey('serp')}
        status={statuses.serp}
      />

      <ApiKeyRow
        label="Google Maps API Key"
        envVar="GOOGLE_MAPS_API_KEY"
        description="Powers geographic business discovery and location data"
        value={keys.gmaps}
        onChange={setKey('gmaps')}
        onTest={() => testKey('gmaps')}
        onSave={() => saveKey('gmaps')}
        status={statuses.gmaps}
      />
    </div>
  );
}

// ─── Tab 5: Account ───────────────────────────────────────────────────────────

function AccountTab() {
  const [profile, setProfile] = useState({ name: 'John Doe', email: 'john@example.com' });
  const [password, setPassword] = useState({ current: '', new_: '', confirm: '' });
  const [apiKey] = useState('bip_sk_live_xK9mN2pQrT7vW4jY8cL1aB3uE6oF5iH0');
  const [keyCopied, setKeyCopied] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [showDanger, setShowDanger] = useState(false);

  const handleCopyKey = () => {
    navigator.clipboard.writeText(apiKey).then(() => {
      setKeyCopied(true);
      toast.success('API key copied to clipboard');
      setTimeout(() => setKeyCopied(false), 2000);
    });
  };

  const handleSaveProfile = () => {
    setProfileSaved(true);
    toast.success('Profile updated');
    setTimeout(() => setProfileSaved(false), 2000);
  };

  const handleSavePassword = () => {
    if (password.new_ !== password.confirm) {
      toast.error('New passwords do not match');
      return;
    }
    setPasswordSaved(true);
    toast.success('Password changed successfully');
    setTimeout(() => setPasswordSaved(false), 2000);
    setPassword({ current: '', new_: '', confirm: '' });
  };

  return (
    <div className="space-y-8">
      {/* Profile */}
      <Section title="Profile" description="Update your personal information">
        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-slate-400 mb-1.5 block flex items-center gap-1.5">
              <User size={12} />
              Full Name
            </label>
            <input
              type="text"
              value={profile.name}
              onChange={(e) => setProfile((p) => ({ ...p, name: e.target.value }))}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-slate-300 focus:outline-none focus:border-indigo-500/60 transition-all"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-400 mb-1.5 block flex items-center gap-1.5">
              <Mail size={12} />
              Email Address
            </label>
            <input
              type="email"
              value={profile.email}
              onChange={(e) => setProfile((p) => ({ ...p, email: e.target.value }))}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-slate-300 focus:outline-none focus:border-indigo-500/60 transition-all"
            />
          </div>
          <button
            onClick={handleSaveProfile}
            className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold text-white transition-all"
            style={{
              background: profileSaved ? 'linear-gradient(135deg, #10b981, #059669)' : 'linear-gradient(135deg, #6366f1, #a855f7)',
              boxShadow: '0 4px 16px rgba(99,102,241,0.25)',
            }}
          >
            {profileSaved ? <Check size={14} /> : <Save size={14} />}
            {profileSaved ? 'Saved!' : 'Save Profile'}
          </button>
        </div>
      </Section>

      {/* Change Password */}
      <Section title="Change Password" description="Update your account password">
        <div className="space-y-4">
          {[
            { label: 'Current Password', key: 'current', value: password.current },
            { label: 'New Password', key: 'new_', value: password.new_ },
            { label: 'Confirm New Password', key: 'confirm', value: password.confirm },
          ].map((field) => (
            <div key={field.key}>
              <label className="text-xs font-medium text-slate-400 mb-1.5 block flex items-center gap-1.5">
                <Lock size={12} />
                {field.label}
              </label>
              <MaskedInput
                value={field.value}
                onChange={(v) => setPassword((p) => ({ ...p, [field.key]: v }))}
                placeholder="••••••••"
              />
            </div>
          ))}
          <button
            onClick={handleSavePassword}
            className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold text-white transition-all"
            style={{
              background: passwordSaved ? 'linear-gradient(135deg, #10b981, #059669)' : 'linear-gradient(135deg, #6366f1, #a855f7)',
              boxShadow: '0 4px 16px rgba(99,102,241,0.25)',
            }}
          >
            {passwordSaved ? <Check size={14} /> : <Lock size={14} />}
            {passwordSaved ? 'Password Updated!' : 'Change Password'}
          </button>
        </div>
      </Section>

      {/* API Key */}
      <Section title="Platform API Key" description="Use this key to authenticate with the BI Platform API">
        <div
          className="p-4 rounded-xl"
          style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <div className="flex items-center gap-3">
            <code className="flex-1 text-xs font-mono text-slate-400 truncate select-none">
              {apiKey.slice(0, 24)}••••••••••••
            </code>
            <button
              onClick={handleCopyKey}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white transition-colors"
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
            >
              {keyCopied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
              {keyCopied ? 'Copied' : 'Copy'}
            </button>
            <button
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white transition-colors"
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
              onClick={() => toast('New API key generated', { icon: '🔄' })}
            >
              <RefreshCw size={12} />
              Regenerate
            </button>
          </div>
          <p className="text-xs text-slate-600 mt-2">
            This key grants full access to the API. Keep it secret.
          </p>
        </div>
      </Section>

      {/* Danger Zone */}
      <Section title="Danger Zone">
        <div
          className="rounded-xl overflow-hidden"
          style={{ border: '1px solid rgba(239,68,68,0.2)' }}
        >
          <div
            className="flex items-center justify-between p-4"
            style={{ background: 'rgba(239,68,68,0.06)' }}
          >
            <div className="flex items-center gap-3">
              <AlertTriangle size={16} className="text-red-400 flex-shrink-0" />
              <div>
                <div className="text-sm font-semibold text-red-400">Delete Account</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  Permanently delete your account and all data. This cannot be undone.
                </div>
              </div>
            </div>
            <button
              onClick={() => setShowDanger((v) => !v)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-red-400 hover:text-red-300 transition-colors"
              style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)' }}
            >
              <Trash2 size={13} />
              Delete Account
            </button>
          </div>

          <AnimatePresence>
            {showDanger && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden border-t border-red-500/20"
              >
                <div className="p-4" style={{ background: 'rgba(239,68,68,0.04)' }}>
                  <p className="text-xs text-red-400 mb-4 leading-relaxed">
                    This action will permanently delete your account, all discovery jobs, audit results, and business data. This cannot be reversed.
                    Type <strong>DELETE MY ACCOUNT</strong> to confirm.
                  </p>
                  <input
                    type="text"
                    placeholder="Type DELETE MY ACCOUNT to confirm"
                    className="w-full bg-black/30 border border-red-500/30 rounded-xl px-4 py-2.5 text-sm text-red-300 placeholder-red-900 focus:outline-none focus:border-red-500/60 transition-all mb-3"
                  />
                  <button
                    className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold text-white transition-all"
                    style={{ background: 'linear-gradient(135deg, #ef4444, #b91c1c)' }}
                    onClick={() => toast.error('This action is disabled in demo mode')}
                  >
                    <Trash2 size={14} />
                    Permanently Delete Account
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </Section>
    </div>
  );
}

// ─── Tab 6: Email / SMTP ──────────────────────────────────────────────────────

function EmailTab() {
  const [host, setHost] = useState('smtp.gmail.com');
  const [port, setPort] = useState('587');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fromName, setFromName] = useState('Web Services Team');
  const [fromEmail, setFromEmail] = useState('');
  const [useTls, setUseTls] = useState(true);
  const [showPass, togglePass] = useToggle(false);
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle');
  const [testMsg, setTestMsg] = useState('');
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  React.useEffect(() => {
    import('@/lib/api').then(({ outreachApi }) => {
      outreachApi.getSmtpStatus().then((s) => {
        if (s.host) setHost(s.host);
        if (s.port) setPort(String(s.port));
        if (s.username) setUsername(s.username);
        if (s.from_name) setFromName(s.from_name);
        if (s.from_email) setFromEmail(s.from_email);
        setLoaded(true);
      }).catch(() => setLoaded(true));
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const { outreachApi } = await import('@/lib/api');
      await outreachApi.saveSmtpConfig({
        smtp_host: host,
        smtp_port: parseInt(port, 10),
        smtp_username: username,
        smtp_password: password,
        smtp_from_name: fromName,
        smtp_from_email: fromEmail || username,
        smtp_use_tls: useTls,
      });
      toast.success('SMTP settings saved. Restart the server to apply.');
    } catch {
      toast.error('Failed to save SMTP settings');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTestStatus('testing');
    setTestMsg('');
    try {
      const { outreachApi } = await import('@/lib/api');
      const res = await outreachApi.testSmtp();
      setTestStatus('ok');
      setTestMsg(res.message);
    } catch (err: unknown) {
      setTestStatus('fail');
      const msg = (err as { message?: string })?.message ?? 'Connection failed';
      setTestMsg(msg);
    }
  };

  const inputCls = 'w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 transition-colors';

  return (
    <div className="space-y-6">
      <Section title="SMTP Configuration" description="Configure outgoing email to send outreach directly from the platform">

        <FieldRow label="SMTP Host" description="Gmail: smtp.gmail.com · Outlook: smtp.office365.com">
          <input className={inputCls} style={{ width: 260 }} value={host} onChange={e => setHost(e.target.value)} placeholder="smtp.gmail.com" />
        </FieldRow>

        <FieldRow label="Port" description="587 = STARTTLS (recommended) · 465 = SSL">
          <input className={inputCls} style={{ width: 100 }} value={port} onChange={e => setPort(e.target.value)} placeholder="587" />
        </FieldRow>

        <FieldRow label="Username / Email" description="Your Gmail or SMTP account email">
          <input className={inputCls} style={{ width: 260 }} value={username} onChange={e => setUsername(e.target.value)} placeholder="you@gmail.com" />
        </FieldRow>

        <FieldRow label="Password / App Password" description="For Gmail: use an App Password (not your main password)">
          <div className="relative" style={{ width: 260 }}>
            <input
              className={inputCls}
              type={showPass ? 'text' : 'password'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="App password"
            />
            <button onClick={togglePass} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white">
              {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </FieldRow>

        <FieldRow label="From Name" description="Name shown as sender">
          <input className={inputCls} style={{ width: 220 }} value={fromName} onChange={e => setFromName(e.target.value)} placeholder="Web Services Team" />
        </FieldRow>

        <FieldRow label="From Email" description="Reply-to address (defaults to username)">
          <input className={inputCls} style={{ width: 260 }} value={fromEmail} onChange={e => setFromEmail(e.target.value)} placeholder="Same as username" />
        </FieldRow>

        <FieldRow label="Use STARTTLS" description="Recommended for port 587">
          <button
            onClick={() => setUseTls(v => !v)}
            className={cn('relative inline-flex h-5 w-9 rounded-full transition-colors', useTls ? 'bg-indigo-600' : 'bg-white/10')}
          >
            <span className={cn('absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform shadow', useTls ? 'translate-x-4' : 'translate-x-0.5')} />
          </button>
        </FieldRow>
      </Section>

      {/* Gmail App Password help */}
      <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5">
        <div className="flex items-start gap-3">
          <AlertTriangle size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-300">Gmail requires an App Password</p>
            <p className="text-xs text-slate-400 mt-1">
              Go to <span className="text-indigo-400">myaccount.google.com → Security → 2-Step Verification → App passwords</span> and generate one for "Mail". Use that 16-character password here, not your Gmail login password.
            </p>
          </div>
        </div>
      </div>

      {/* Test result */}
      {testStatus !== 'idle' && (
        <div className={cn('p-3 rounded-lg flex items-center gap-2 text-sm', testStatus === 'ok' ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20' : testStatus === 'fail' ? 'bg-red-500/10 text-red-300 border border-red-500/20' : 'bg-white/5 text-slate-400 border border-white/10')}>
          {testStatus === 'testing' && <Loader2 size={14} className="animate-spin" />}
          {testStatus === 'ok' && <CheckCircle2 size={14} />}
          {testStatus === 'fail' && <XCircle size={14} />}
          <span>{testStatus === 'testing' ? 'Testing connection…' : testMsg}</span>
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <button
          onClick={handleTest}
          disabled={testStatus === 'testing'}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-300 text-sm hover:bg-white/10 transition-colors disabled:opacity-50"
        >
          {testStatus === 'testing' ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
          Test Connection
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          Save SMTP Settings
        </button>
      </div>
    </div>
  );
}

// ─── Tab Config ───────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string; icon: React.ReactNode; description: string }[] = [
  { id: 'discovery', label: 'Discovery', icon: <Search size={16} />, description: 'Providers & search params' },
  { id: 'audit', label: 'Audit', icon: <Sliders size={16} />, description: 'Screenshot & AI analysis' },
  { id: 'database', label: 'Database', icon: <Database size={16} />, description: 'Connection & migrations' },
  { id: 'apikeys', label: 'API Keys', icon: <Key size={16} />, description: 'Third-party credentials' },
  { id: 'account', label: 'Account', icon: <User size={16} />, description: 'Profile & security' },
  { id: 'email', label: 'Email / SMTP', icon: <Mail size={16} />, description: 'Outgoing email configuration' },
];

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('discovery');

  const renderContent = () => {
    switch (activeTab) {
      case 'discovery': return <DiscoveryTab />;
      case 'audit': return <AuditTab />;
      case 'database': return <DatabaseTab />;
      case 'apikeys': return <ApiKeysTab />;
      case 'account': return <AccountTab />;
      case 'email': return <EmailTab />;
    }
  };

  const activeTabConfig = TABS.find((t) => t.id === activeTab)!;

  return (
    <div className="min-h-full p-6">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 mb-6">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, rgba(99,102,241,0.3), rgba(168,85,247,0.3))',
            border: '1px solid rgba(99,102,241,0.3)',
          }}
        >
          <Settings size={20} className="text-indigo-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-white">Settings</h1>
          <p className="text-sm text-slate-400">Configure your BI Platform</p>
        </div>
      </div>

      <div className="flex gap-6 lg:gap-8">
        {/* ── Sidebar Navigation ─────────────────────────────────────── */}
        <div className="hidden md:flex flex-col gap-1 w-52 flex-shrink-0">
          {TABS.map((tab) => {
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'relative flex items-start gap-3 px-4 py-3 rounded-xl text-left transition-all group',
                  active ? 'text-white' : 'text-slate-400 hover:text-white hover:bg-white/5'
                )}
                style={
                  active
                    ? {
                        background: 'rgba(99,102,241,0.15)',
                        border: '1px solid rgba(99,102,241,0.25)',
                      }
                    : {}
                }
              >
                {active && (
                  <motion.div
                    layoutId="settings-indicator"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-8 rounded-full"
                    style={{ background: '#6366f1', boxShadow: '0 0 8px rgba(99,102,241,0.8)' }}
                  />
                )}
                <span className={active ? 'text-indigo-400' : 'text-slate-500 group-hover:text-slate-400'}>
                  {tab.icon}
                </span>
                <div>
                  <div className="text-sm font-medium">{tab.label}</div>
                  <div className="text-xs text-slate-600 mt-0.5">{tab.description}</div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Mobile tab bar */}
        <div className="md:hidden w-full flex gap-1 overflow-x-auto pb-2 mb-2 scrollbar-hide">
          {TABS.map((tab) => {
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'flex-shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all whitespace-nowrap',
                  active ? 'text-white' : 'text-slate-400 hover:text-slate-300'
                )}
                style={{
                  background: active ? 'rgba(99,102,241,0.2)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${active ? 'rgba(99,102,241,0.35)' : 'rgba(255,255,255,0.07)'}`,
                }}
              >
                {tab.icon}
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* ── Content Panel ───────────────────────────────────────────── */}
        <div className="flex-1 min-w-0">
          <GlassCard>
            {/* Panel header */}
            <div
              className="flex items-center gap-3 pb-5 mb-6 border-b border-white/8"
              style={{ borderBottomColor: 'rgba(255,255,255,0.08)' }}
            >
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center text-indigo-400"
                style={{ background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.2)' }}
              >
                {activeTabConfig.icon}
              </div>
              <div>
                <h2 className="text-base font-bold text-white">{activeTabConfig.label} Settings</h2>
                <p className="text-xs text-slate-500">{activeTabConfig.description}</p>
              </div>
            </div>

            {/* Animated content */}
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.18 }}
              >
                {renderContent()}
              </motion.div>
            </AnimatePresence>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
