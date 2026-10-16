'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { crmApi, type DealRaw, type PipelineRaw } from '@/lib/api';
import {
  Briefcase,
  Plus,
  DollarSign,
  TrendingUp,
  CheckCircle2,
  XCircle,
  ChevronRight,
  Edit3,
  Trash2,
  Building2,
  BarChart2,
  Award,
  AlertCircle,
} from 'lucide-react';
import GlassCard from '@/components/ui/GlassCard';
import Badge from '@/components/ui/Badge';
import LoadingSpinner from '@/components/ui/LoadingSpinner';
import EmptyState from '@/components/ui/EmptyState';

const STAGE_COLORS: Record<string, string> = {
  lead: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
  contacted: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  qualified: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  proposal_sent: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  negotiation: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  won: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  lost: 'bg-red-500/20 text-red-300 border-red-500/30',
};

const STAGES = ['lead', 'contacted', 'qualified', 'proposal_sent', 'negotiation', 'won', 'lost'];

function formatCurrency(val: number): string {
  if (val >= 1000) return `$${(val / 1000).toFixed(1)}k`;
  return `$${val.toFixed(0)}`;
}

export default function CRMPage() {
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null);
  const [view, setView] = useState<'kanban' | 'list'>('kanban');
  const queryClient = useQueryClient();

  const { data: pipelines = [], isLoading: pipelinesLoading } = useQuery<PipelineRaw[]>({
    queryKey: ['crm-pipelines'],
    queryFn: crmApi.listPipelines,
  });

  // Auto-select first pipeline
  React.useEffect(() => {
    if (pipelines.length > 0 && !selectedPipeline) {
      setSelectedPipeline(pipelines[0].id);
    }
  }, [pipelines, selectedPipeline]);

  const { data: deals = [], isLoading: dealsLoading } = useQuery({
    queryKey: ['crm-deals', selectedPipeline],
    queryFn: () => crmApi.listDeals({ pipeline_id: selectedPipeline || undefined, limit: 200 }),
    enabled: !!selectedPipeline,
  });

  const { data: pipelineStats } = useQuery({
    queryKey: ['crm-pipeline-stats', selectedPipeline],
    queryFn: () => crmApi.pipelineStats(selectedPipeline!),
    enabled: !!selectedPipeline,
  });

  const updateDealMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<DealRaw> }) =>
      crmApi.updateDeal(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-deals'] });
      queryClient.invalidateQueries({ queryKey: ['crm-pipeline-stats'] });
    },
  });

  const deleteDealMutation = useMutation({
    mutationFn: crmApi.deleteDeal,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['crm-deals'] }),
  });

  const dealsByStage = STAGES.reduce<Record<string, DealRaw[]>>((acc, stage) => {
    acc[stage] = deals.filter((d) => d.stage === stage);
    return acc;
  }, {});

  if (pipelinesLoading) {
    return <div className="flex justify-center py-24"><LoadingSpinner /></div>;
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">CRM Pipeline</h1>
          <p className="text-slate-400 text-sm mt-1">Track deals from lead to close</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setView('kanban')}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${view === 'kanban' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white hover:bg-white/5'}`}
          >
            Kanban
          </button>
          <button
            onClick={() => setView('list')}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${view === 'list' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white hover:bg-white/5'}`}
          >
            List
          </button>
        </div>
      </div>

      {/* Pipeline selector */}
      {pipelines.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {pipelines.map((p) => (
            <button
              key={p.id}
              onClick={() => setSelectedPipeline(p.id)}
              className={`px-4 py-2 text-sm rounded-lg whitespace-nowrap transition-colors ${
                selectedPipeline === p.id
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white/5 text-slate-400 hover:text-white border border-white/10'
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}

      {/* Stats Row */}
      {pipelineStats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Deals', value: pipelineStats.total_deals, icon: <Briefcase size={16} />, color: 'text-indigo-400' },
            { label: 'Pipeline Value', value: formatCurrency(pipelineStats.total_value), icon: <DollarSign size={16} />, color: 'text-emerald-400' },
            { label: 'Won', value: `${pipelineStats.won_count} deals`, icon: <CheckCircle2 size={16} />, color: 'text-green-400' },
            { label: 'Won Value', value: formatCurrency(pipelineStats.won_value), icon: <TrendingUp size={16} />, color: 'text-yellow-400' },
          ].map((s) => (
            <GlassCard key={s.label} className="p-4">
              <div className="flex items-center gap-3">
                <div className={s.color}>{s.icon}</div>
                <div>
                  <p className="text-lg font-bold text-white">{s.value}</p>
                  <p className="text-xs text-slate-400">{s.label}</p>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {pipelines.length === 0 ? (
        <EmptyState
          icon={<Briefcase size={40} className="text-slate-600" />}
          title="No pipelines yet"
          description="Create a pipeline to start tracking your deals."
        />
      ) : dealsLoading ? (
        <div className="flex justify-center py-12"><LoadingSpinner /></div>
      ) : view === 'kanban' ? (
        /* Kanban view */
        <div className="flex gap-4 overflow-x-auto pb-4" style={{ minHeight: '400px' }}>
          {STAGES.filter(s => s !== 'lost').map((stage) => (
            <div key={stage} className="flex-shrink-0 w-72">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-slate-300 capitalize">{stage.replace('_', ' ')}</h3>
                <span className="text-xs text-slate-500 bg-white/5 px-2 py-0.5 rounded-full">
                  {dealsByStage[stage]?.length || 0}
                </span>
              </div>
              <div className="space-y-3">
                {(dealsByStage[stage] || []).map((deal) => (
                  <GlassCard key={deal.id} className="p-3 hover:border-white/20 transition-colors">
                    <div className="flex items-start justify-between mb-2">
                      <p className="text-sm font-medium text-white">{deal.title}</p>
                      <button
                        onClick={() => deleteDealMutation.mutate(deal.id)}
                        className="text-slate-500 hover:text-red-400 transition-colors ml-2 flex-shrink-0"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                    <p className="text-lg font-bold text-emerald-400">{formatCurrency(deal.value)}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <div className="flex gap-1">
                        {STAGES.filter(s => s !== 'lost').map((s, i) => (
                          <button
                            key={s}
                            onClick={() => updateDealMutation.mutate({ id: deal.id, payload: { stage: s } })}
                            className={`w-2 h-2 rounded-full transition-colors ${s === deal.stage ? 'bg-indigo-400' : 'bg-slate-600 hover:bg-slate-400'}`}
                            title={s.replace('_', ' ')}
                          />
                        ))}
                      </div>
                    </div>
                  </GlassCard>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* List view */
        <GlassCard>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10">
                  {['Title', 'Stage', 'Value', 'Probability', 'Created'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {deals.map((deal) => (
                  <tr key={deal.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                    <td className="px-4 py-3 text-white">{deal.title}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full border font-medium capitalize ${STAGE_COLORS[deal.stage] || STAGE_COLORS.lead}`}>
                        {deal.stage.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-emerald-400 font-semibold">{formatCurrency(deal.value)}</td>
                    <td className="px-4 py-3 text-slate-300">{deal.probability}%</td>
                    <td className="px-4 py-3 text-slate-500">{new Date(deal.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
                {deals.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-500">No deals in this pipeline</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}
    </div>
  );
}
