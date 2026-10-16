'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { proposalsApi, type ProposalRaw } from '@/lib/api';
import {
  FileText,
  Plus,
  Send,
  Eye,
  CheckCircle2,
  XCircle,
  Clock,
  DollarSign,
  ExternalLink,
  Trash2,
  AlertCircle,
  Zap,
  ChevronDown,
  ChevronRight,
  Calendar,
  TrendingUp,
} from 'lucide-react';
import GlassCard from '@/components/ui/GlassCard';
import LoadingSpinner from '@/components/ui/LoadingSpinner';
import EmptyState from '@/components/ui/EmptyState';

const STATUS_ICONS: Record<string, React.ReactNode> = {
  draft: <Clock size={14} className="text-slate-400" />,
  generated: <FileText size={14} className="text-indigo-400" />,
  sent: <Send size={14} className="text-blue-400" />,
  viewed: <Eye size={14} className="text-yellow-400" />,
  accepted: <CheckCircle2 size={14} className="text-emerald-400" />,
  rejected: <XCircle size={14} className="text-red-400" />,
  expired: <AlertCircle size={14} className="text-slate-500" />,
};

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-slate-500/20 text-slate-300',
  generated: 'bg-indigo-500/20 text-indigo-300',
  sent: 'bg-blue-500/20 text-blue-300',
  viewed: 'bg-yellow-500/20 text-yellow-300',
  accepted: 'bg-emerald-500/20 text-emerald-300',
  rejected: 'bg-red-500/20 text-red-300',
  expired: 'bg-slate-600/20 text-slate-500',
};

function formatCurrency(v: number): string {
  if (v >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  return `$${v.toFixed(0)}`;
}

export default function ProposalsPage() {
  const [businessId, setBusinessId] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const queryClient = useQueryClient();

  const { data: proposals = [], isLoading } = useQuery({
    queryKey: ['proposals'],
    queryFn: () => proposalsApi.list({ limit: 100 }),
  });

  const generateMutation = useMutation({
    mutationFn: proposalsApi.generate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals'] });
      setBusinessId('');
      setGenerating(false);
    },
    onError: () => setGenerating(false),
  });

  const markSentMutation = useMutation({
    mutationFn: proposalsApi.markSent,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['proposals'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: proposalsApi.delete,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['proposals'] }),
  });

  const stats = {
    total: proposals.length,
    generated: proposals.filter((p) => p.status === 'generated').length,
    sent: proposals.filter((p) => p.status === 'sent').length,
    accepted: proposals.filter((p) => p.status === 'accepted').length,
    totalValue: proposals.reduce((sum, p) => sum + p.total_value, 0),
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Proposals</h1>
          <p className="text-slate-400 text-sm mt-1">AI-generated proposals based on audit findings</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: 'Total', value: stats.total, icon: <FileText size={16} />, color: 'text-indigo-400' },
          { label: 'Generated', value: stats.generated, icon: <Zap size={16} />, color: 'text-purple-400' },
          { label: 'Sent', value: stats.sent, icon: <Send size={16} />, color: 'text-blue-400' },
          { label: 'Accepted', value: stats.accepted, icon: <CheckCircle2 size={16} />, color: 'text-emerald-400' },
          { label: 'Total Value', value: formatCurrency(stats.totalValue), icon: <DollarSign size={16} />, color: 'text-yellow-400' },
        ].map((s) => (
          <GlassCard key={s.label} className="p-4">
            <div className="flex items-center gap-2">
              <div className={s.color}>{s.icon}</div>
              <div>
                <p className="text-lg font-bold text-white">{s.value}</p>
                <p className="text-xs text-slate-400">{s.label}</p>
              </div>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Generate Form */}
      <GlassCard className="p-5">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Zap size={16} className="text-yellow-400" />
          Generate New Proposal
        </h3>
        <div className="flex gap-3">
          <input
            type="text"
            value={businessId}
            onChange={(e) => setBusinessId(e.target.value)}
            placeholder="Business UUID..."
            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50"
          />
          <button
            onClick={() => {
              if (!businessId) return;
              setGenerating(true);
              generateMutation.mutate({ business_id: businessId });
            }}
            disabled={!businessId || generateMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            {generateMutation.isPending ? (
              <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Generating...</>
            ) : (
              <><Zap size={14} /> Generate</>
            )}
          </button>
        </div>
        <p className="text-xs text-slate-500 mt-2">
          The system will use the latest audit for the business to create a personalised proposal.
        </p>
      </GlassCard>

      {/* Proposals List */}
      {isLoading ? (
        <div className="flex justify-center py-12"><LoadingSpinner /></div>
      ) : proposals.length === 0 ? (
        <EmptyState
          icon={<FileText size={40} className="text-slate-600" />}
          title="No proposals yet"
          description="Generate a proposal by entering a business ID above."
        />
      ) : (
        <div className="space-y-3">
          {proposals.map((proposal) => (
            <GlassCard key={proposal.id} className="overflow-hidden">
              <div
                className="p-4 flex items-center gap-4 cursor-pointer hover:bg-white/2 transition-colors"
                onClick={() => setExpanded(expanded === proposal.id ? null : proposal.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <p className="font-semibold text-white truncate">{proposal.title}</p>
                    <span className={`text-xs px-2 py-0.5 rounded-full flex items-center gap-1 flex-shrink-0 ${STATUS_COLORS[proposal.status] || STATUS_COLORS.draft}`}>
                      {STATUS_ICONS[proposal.status]}
                      {proposal.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <DollarSign size={10} />
                      {formatCurrency(proposal.total_value)}
                    </span>
                    {proposal.valid_until && (
                      <span className="flex items-center gap-1">
                        <Calendar size={10} />
                        Valid until {new Date(proposal.valid_until).toLocaleDateString()}
                      </span>
                    )}
                    <span>{new Date(proposal.created_at).toLocaleDateString()}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {(proposal.status === 'generated' || proposal.status === 'draft') && (
                    <button
                      onClick={(e) => { e.stopPropagation(); markSentMutation.mutate(proposal.id); }}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600/20 text-blue-400 rounded-lg text-xs hover:bg-blue-600/30 transition-colors"
                      title="Mark as sent"
                    >
                      <Send size={12} /> Mark Sent
                    </button>
                  )}
                  <a
                    href={proposalsApi.getHtmlUrl(proposal.id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="p-1.5 text-slate-400 hover:text-white transition-colors"
                    title="View HTML"
                  >
                    <ExternalLink size={14} />
                  </a>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(proposal.id); }}
                    className="p-1.5 text-slate-400 hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                  {expanded === proposal.id ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                </div>
              </div>

              {expanded === proposal.id && (
                <div className="border-t border-white/10 p-4 bg-white/2 space-y-4">
                  {proposal.executive_summary && (
                    <div>
                      <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Executive Summary</h5>
                      <p className="text-sm text-slate-300">{proposal.executive_summary}</p>
                    </div>
                  )}

                  {proposal.problems_identified && proposal.problems_identified.length > 0 && (
                    <div>
                      <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Issues Identified</h5>
                      <div className="space-y-2">
                        {proposal.problems_identified.map((p, i) => (
                          <div key={i} className="flex items-start gap-2 text-sm">
                            <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                              p.severity === 'critical' ? 'bg-red-500' :
                              p.severity === 'high' ? 'bg-orange-500' :
                              p.severity === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
                            }`} />
                            <div>
                              <span className="font-medium text-white">{p.title}</span>
                              <p className="text-slate-400 text-xs mt-0.5">{p.impact}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {proposal.solutions_proposed && proposal.solutions_proposed.length > 0 && (
                    <div>
                      <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Recommended Solutions</h5>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {proposal.solutions_proposed.map((s, i) => (
                          <div key={i} className="bg-white/5 rounded-lg p-3">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-sm font-medium text-white">{s.title}</span>
                              <span className="text-xs text-emerald-400 font-semibold">
                                ${s.price_min.toLocaleString()}–${s.price_max.toLocaleString()}
                                {s.recurring && `/${s.period}`}
                              </span>
                            </div>
                            <p className="text-xs text-slate-400">{s.timeline_weeks} weeks</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {proposal.expected_roi && (
                    <div>
                      <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Expected ROI</h5>
                      <p className="text-sm text-slate-300">{proposal.expected_roi}</p>
                    </div>
                  )}
                </div>
              )}
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}
