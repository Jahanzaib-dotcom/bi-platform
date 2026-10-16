'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { outreachApi, businessesApi, type CampaignRaw, type EmailTemplateRaw } from '@/lib/api';
import {
  Mail,
  Plus,
  Play,
  Pause,
  BarChart2,
  Send,
  Users,
  Eye,
  MousePointerClick,
  Reply,
  AlertCircle,
  CheckCircle2,
  Linkedin,
  Pencil,
  Copy,
  Trash2,
  ChevronDown,
  ChevronRight,
  FileText,
  Zap,
  Filter,
} from 'lucide-react';
import GlassCard from '@/components/ui/GlassCard';
import Badge from '@/components/ui/Badge';
import LoadingSpinner from '@/components/ui/LoadingSpinner';
import EmptyState from '@/components/ui/EmptyState';

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-slate-500/20 text-slate-300',
  active: 'bg-emerald-500/20 text-emerald-300',
  paused: 'bg-yellow-500/20 text-yellow-300',
  completed: 'bg-blue-500/20 text-blue-300',
  cancelled: 'bg-red-500/20 text-red-300',
};

function StatMini({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center">
      <div className="text-slate-400 mb-1">{icon}</div>
      <p className="text-sm font-bold text-white">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}

export default function OutreachPage() {
  const [activeTab, setActiveTab] = useState<'campaigns' | 'templates' | 'generate'>('campaigns');
  const [selectedBizId, setSelectedBizId] = useState('');
  const [senderName, setSenderName] = useState('Web Services Team');
  const [generatedEmail, setGeneratedEmail] = useState<{ subject: string; body_html: string; body_text: string } | null>(null);
  const [linkedinMessage, setLinkedinMessage] = useState('');
  const [expandedCampaign, setExpandedCampaign] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const { data: campaigns = [], isLoading: campaignsLoading } = useQuery({
    queryKey: ['outreach-campaigns'],
    queryFn: () => outreachApi.listCampaigns({ limit: 50 }),
  });

  const { data: templates = [], isLoading: templatesLoading } = useQuery({
    queryKey: ['outreach-templates'],
    queryFn: () => outreachApi.listTemplates(),
  });

  const { data: campaignStats } = useQuery({
    queryKey: ['campaign-stats', expandedCampaign],
    queryFn: () => outreachApi.campaignStats(expandedCampaign!),
    enabled: !!expandedCampaign,
  });

  const startMutation = useMutation({
    mutationFn: outreachApi.startCampaign,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['outreach-campaigns'] }),
  });

  const pauseMutation = useMutation({
    mutationFn: outreachApi.pauseCampaign,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['outreach-campaigns'] }),
  });

  const generateMutation = useMutation({
    mutationFn: (params: { business_id: string; sender_name: string }) =>
      outreachApi.generateEmail({ ...params, template_type: 'initial_outreach' }),
    onSuccess: (data) => setGeneratedEmail(data),
  });

  const linkedinMutation = useMutation({
    mutationFn: (business_id: string) => outreachApi.generateLinkedIn({ business_id }),
    onSuccess: (data) => setLinkedinMessage(data.message),
  });

  const totalStats = campaigns.reduce(
    (acc, c) => ({
      sent: acc.sent + c.sent_count,
      opened: acc.opened + c.opened_count,
      replied: acc.replied + c.replied_count,
    }),
    { sent: 0, opened: 0, replied: 0 }
  );

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Outreach Center</h1>
          <p className="text-slate-400 text-sm mt-1">Personalized email and LinkedIn outreach</p>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Emails Sent', value: totalStats.sent, icon: <Send size={16} />, color: 'text-indigo-400' },
          { label: 'Opened', value: totalStats.opened, icon: <Eye size={16} />, color: 'text-emerald-400' },
          { label: 'Replies', value: totalStats.replied, icon: <Reply size={16} />, color: 'text-purple-400' },
        ].map((s) => (
          <GlassCard key={s.label} className="p-4">
            <div className="flex items-center gap-3">
              <div className={s.color}>{s.icon}</div>
              <div>
                <p className="text-2xl font-bold text-white">{s.value}</p>
                <p className="text-xs text-slate-400">{s.label}</p>
              </div>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white/5 p-1 rounded-lg w-fit">
        {(['campaigns', 'templates', 'generate'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm rounded-md transition-colors capitalize ${
              activeTab === tab ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Campaigns Tab */}
      {activeTab === 'campaigns' && (
        campaignsLoading ? (
          <div className="flex justify-center py-12"><LoadingSpinner /></div>
        ) : campaigns.length === 0 ? (
          <EmptyState
            icon={<Mail size={40} className="text-slate-600" />}
            title="No campaigns yet"
            description="Create campaigns to reach out to your discovered leads at scale."
          />
        ) : (
          <div className="space-y-3">
            {campaigns.map((campaign) => (
              <GlassCard key={campaign.id} className="overflow-hidden">
                <div
                  className="p-4 flex items-center gap-4 cursor-pointer"
                  onClick={() => setExpandedCampaign(expandedCampaign === campaign.id ? null : campaign.id)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <span className="font-semibold text-white">{campaign.name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[campaign.status] || STATUS_COLORS.draft}`}>
                        {campaign.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-slate-500">
                      <span>{campaign.total_recipients} recipients</span>
                      <span>{campaign.sent_count} sent</span>
                      <span>{campaign.opened_count} opened</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    {campaign.status === 'draft' || campaign.status === 'paused' ? (
                      <button
                        onClick={(e) => { e.stopPropagation(); startMutation.mutate(campaign.id); }}
                        className="p-2 bg-emerald-500/20 text-emerald-400 rounded-lg hover:bg-emerald-500/30 transition-colors"
                        title="Start"
                      >
                        <Play size={14} />
                      </button>
                    ) : campaign.status === 'active' ? (
                      <button
                        onClick={(e) => { e.stopPropagation(); pauseMutation.mutate(campaign.id); }}
                        className="p-2 bg-yellow-500/20 text-yellow-400 rounded-lg hover:bg-yellow-500/30 transition-colors"
                        title="Pause"
                      >
                        <Pause size={14} />
                      </button>
                    ) : null}
                    {expandedCampaign === campaign.id ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                  </div>
                </div>

                {expandedCampaign === campaign.id && campaignStats && (
                  <div className="border-t border-white/10 p-4 bg-white/2">
                    <div className="grid grid-cols-5 gap-4">
                      <StatMini label="Total" value={campaignStats.total} icon={<Users size={14} />} />
                      <StatMini label="Sent" value={campaignStats.sent} icon={<Send size={14} />} />
                      <StatMini label="Open Rate" value={`${campaignStats.open_rate.toFixed(1)}%`} icon={<Eye size={14} />} />
                      <StatMini label="Click Rate" value={`${campaignStats.click_rate.toFixed(1)}%`} icon={<MousePointerClick size={14} />} />
                      <StatMini label="Reply Rate" value={`${campaignStats.reply_rate.toFixed(1)}%`} icon={<Reply size={14} />} />
                    </div>
                  </div>
                )}
              </GlassCard>
            ))}
          </div>
        )
      )}

      {/* Templates Tab */}
      {activeTab === 'templates' && (
        templatesLoading ? (
          <div className="flex justify-center py-12"><LoadingSpinner /></div>
        ) : templates.length === 0 ? (
          <EmptyState
            icon={<FileText size={40} className="text-slate-600" />}
            title="No templates yet"
            description="Create email templates to use in your campaigns."
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {templates.map((t) => (
              <GlassCard key={t.id} className="p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <p className="font-semibold text-white">{t.name}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{t.template_type.replace('_', ' ')}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${t.is_active ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-500/20 text-slate-400'}`}>
                    {t.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <p className="text-sm text-slate-300 font-medium">{t.subject}</p>
                {t.industry_target && (
                  <p className="text-xs text-indigo-400 mt-1">For: {t.industry_target}</p>
                )}
              </GlassCard>
            ))}
          </div>
        )
      )}

      {/* Generate Tab */}
      {activeTab === 'generate' && (
        <div className="space-y-4">
          <GlassCard className="p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Zap size={18} className="text-yellow-400" />
              AI-Powered Email Generator
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1.5">Business ID</label>
                <input
                  type="text"
                  value={selectedBizId}
                  onChange={(e) => setSelectedBizId(e.target.value)}
                  placeholder="Paste a business UUID..."
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1.5">Sender Name</label>
                <input
                  type="text"
                  value={senderName}
                  onChange={(e) => setSenderName(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/50"
                />
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => generateMutation.mutate({ business_id: selectedBizId, sender_name: senderName })}
                disabled={!selectedBizId || generateMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              >
                <Mail size={14} />
                Generate Email
              </button>
              <button
                onClick={() => linkedinMutation.mutate(selectedBizId)}
                disabled={!selectedBizId || linkedinMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-blue-700 hover:bg-blue-800 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              >
                <Linkedin size={14} />
                LinkedIn Message
              </button>
            </div>
          </GlassCard>

          {generatedEmail && (
            <GlassCard className="p-6">
              <h4 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <CheckCircle2 size={14} className="text-emerald-400" />
                Generated Email
              </h4>
              <div className="bg-white/5 rounded-lg p-3 mb-3">
                <p className="text-xs text-slate-400 mb-1">Subject</p>
                <p className="text-white font-medium">{generatedEmail.subject}</p>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <p className="text-xs text-slate-400 mb-2">Body</p>
                <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans">{generatedEmail.body_text}</pre>
              </div>
            </GlassCard>
          )}

          {linkedinMessage && (
            <GlassCard className="p-6">
              <h4 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <Linkedin size={14} className="text-blue-400" />
                LinkedIn Message
              </h4>
              <div className="bg-white/5 rounded-lg p-3">
                <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans">{linkedinMessage}</pre>
              </div>
            </GlassCard>
          )}
        </div>
      )}
    </div>
  );
}
