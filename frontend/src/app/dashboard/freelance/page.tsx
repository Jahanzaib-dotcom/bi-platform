'use client';

import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Briefcase,
  Search,
  ExternalLink,
  Copy,
  Check,
  Bookmark,
  Sparkles,
  RefreshCw,
  DollarSign,
  CheckCircle2,
  Clock,
  Send,
  Layers,
  ArrowUpRight,
  Filter,
  TrendingUp,
  Globe,
  SlidersHorizontal,
  X,
} from 'lucide-react';

import { freelanceApi, FreelanceJobRaw } from '@/lib/api';

const QUICK_NICHES = [
  { label: 'Shopify Store', icon: '🛍️', query: 'shopify store' },
  { label: 'WordPress / Elementor', icon: '🌐', query: 'wordpress website' },
  { label: 'Full-Stack Web App', icon: '⚡', query: 'web application react nextjs' },
  { label: 'E-Commerce Website', icon: '🛒', query: 'ecommerce website design' },
  { label: 'Figma to Website', icon: '🎨', query: 'figma to html react' },
  { label: 'Landing Page & Funnel', icon: '🚀', query: 'landing page high converting' },
];

export default function FreelancePage() {
  const queryClient = useQueryClient();

  const [searchQuery, setSearchQuery] = useState('shopify website');
  const [activeQuery, setActiveQuery] = useState('shopify website');
  const [selectedPlatform, setSelectedPlatform] = useState<string>('all');
  const [activeTab, setActiveTab] = useState<'live' | 'saved'>('live');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [selectedJob, setSelectedJob] = useState<FreelanceJobRaw | null>(null);

  // Live jobs query
  const {
    data: liveData,
    isLoading: isLoadingLive,
    isFetching: isFetchingLive,
    refetch: refetchLive,
  } = useQuery({
    queryKey: ['freelance', 'live-jobs', activeQuery, selectedPlatform],
    queryFn: () =>
      freelanceApi.searchLive({
        query: activeQuery,
        platform: selectedPlatform === 'all' ? undefined : selectedPlatform,
        limit: 30,
      }),
    staleTime: 60 * 1000,
  });

  // Saved leads query
  const { data: savedData, isLoading: isLoadingSaved } = useQuery({
    queryKey: ['freelance', 'saved-leads'],
    queryFn: () => freelanceApi.listSaved(),
    enabled: activeTab === 'saved',
  });

  // Save to CRM mutation
  const saveMutation = useMutation({
    mutationFn: (job: FreelanceJobRaw) =>
      freelanceApi.saveToCrm({
        title: job.title,
        platform: job.platform,
        project_url: job.project_url,
        budget: job.budget,
        description: job.description,
        pitch: job.pitch,
      }),
    onSuccess: (_, job) => {
      setSavedIds((prev) => new Set(prev).add(job.id));
      queryClient.invalidateQueries({ queryKey: ['freelance', 'saved-leads'] });
      queryClient.invalidateQueries({ queryKey: ['crm', 'deals'] });
    },
  });

  const handleCopyPitch = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2500);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setActiveQuery(searchQuery.trim());
    }
  };

  const handleQuickNiche = (query: string) => {
    setSearchQuery(query);
    setActiveQuery(query);
  };

  const jobsList = liveData?.items ?? [];

  return (
      <div className="min-h-screen bg-[#070714] text-white p-6 lg:p-8 space-y-8">
        {/* ── Top Header Banner ── */}
        <div className="relative rounded-2xl overflow-hidden border border-white/10 bg-gradient-to-r from-indigo-950/60 via-purple-950/40 to-slate-950/80 p-6 lg:p-8 backdrop-blur-xl shadow-2xl">
          <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute bottom-0 left-1/3 -mb-12 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

          <div className="relative z-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div className="space-y-2 max-w-2xl">
              <div className="flex items-center gap-2.5">
                <div className="p-2.5 rounded-xl bg-indigo-500/20 border border-indigo-500/30 text-indigo-400">
                  <Briefcase size={24} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h1 className="text-2xl lg:text-3xl font-black text-white tracking-tight">
                      Freelance Client Hub
                    </h1>
                    <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold text-emerald-300 bg-emerald-500/15 border border-emerald-500/30 animate-pulse">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> LIVE
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">
                    Direct clients &amp; paying projects from <strong className="text-emerald-400 font-semibold">Upwork</strong>, <strong className="text-sky-400 font-semibold">Freelancer.com</strong>, and <strong className="text-teal-400 font-semibold">Fiverr</strong> with AI proposal generation.
                  </p>
                </div>
              </div>
            </div>

            {/* Quick Stats Badges */}
            <div className="flex items-center gap-3 flex-wrap">
              <div className="px-3.5 py-2 rounded-xl bg-white/5 border border-white/10 text-center">
                <div className="text-xs text-slate-400 font-medium">Ban-Safe</div>
                <div className="text-sm font-bold text-emerald-400">100% Compliant</div>
              </div>
              <div className="px-3.5 py-2 rounded-xl bg-white/5 border border-white/10 text-center">
                <div className="text-xs text-slate-400 font-medium">Proposal Mode</div>
                <div className="text-sm font-bold text-indigo-300">1-Click Auto-Copy</div>
              </div>
              <button
                onClick={() => refetchLive()}
                disabled={isFetchingLive}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-500 transition-all shadow-lg hover:shadow-indigo-500/25 disabled:opacity-50 cursor-pointer"
              >
                <RefreshCw size={14} className={isFetchingLive ? 'animate-spin' : ''} />
                <span>{isFetchingLive ? 'Scanning Feeds...' : 'Refresh Live Jobs'}</span>
              </button>
            </div>
          </div>

          {/* Sub Navigation Tabs */}
          <div className="flex items-center gap-2 mt-6 pt-5 border-t border-white/10">
            <button
              onClick={() => setActiveTab('live')}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'live'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <TrendingUp size={14} />
              <span>Live Opportunities ({jobsList.length})</span>
            </button>
            <button
              onClick={() => setActiveTab('saved')}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'saved'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Bookmark size={14} />
              <span>Saved in CRM Pipeline ({savedData?.total ?? savedIds.size})</span>
            </button>
          </div>
        </div>

        {/* ── Search & Filter Controls ── */}
        {activeTab === 'live' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
              {/* Search input form */}
              <form onSubmit={handleSearchSubmit} className="md:col-span-8 flex items-center gap-2">
                <div className="relative flex-1">
                  <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search keywords e.g. 'Shopify clothing store', 'WordPress clinic', 'Next.js developer'..."
                    className="w-full pl-10 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/50 transition-all"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => setSearchQuery('')}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
                <button
                  type="submit"
                  disabled={isFetchingLive}
                  className="px-5 py-3 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 transition-all flex items-center gap-2 flex-shrink-0 cursor-pointer shadow-md"
                >
                  <Search size={14} />
                  <span>Search</span>
                </button>
              </form>

              {/* Platform Filter Buttons */}
              <div className="md:col-span-4 flex items-center gap-1.5 p-1 rounded-xl bg-white/5 border border-white/10">
                {[
                  { id: 'all', label: 'All', icon: '🌐' },
                  { id: 'freelancer', label: 'Freelancer', icon: '🔵' },
                  { id: 'upwork', label: 'Upwork', icon: '🟢' },
                  { id: 'fiverr', label: 'Fiverr', icon: '🟢' },
                ].map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setSelectedPlatform(p.id)}
                    className={`flex-1 py-2 px-2.5 rounded-lg text-xs font-semibold transition-all cursor-pointer text-center ${
                      selectedPlatform === p.id
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'text-slate-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <span>{p.icon} {p.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Quick Niche Suggestion Chips */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
              <span className="text-xs text-slate-500 font-medium whitespace-nowrap flex items-center gap-1">
                <Sparkles size={12} className="text-amber-400" /> Quick Niches:
              </span>
              {QUICK_NICHES.map((niche) => (
                <button
                  key={niche.label}
                  onClick={() => handleQuickNiche(niche.query)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all border cursor-pointer ${
                    activeQuery === niche.query
                      ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                      : 'bg-white/5 text-slate-300 border-white/10 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  <span className="mr-1">{niche.icon}</span>
                  {niche.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Content Grid / Active View ── */}
        {activeTab === 'live' ? (
          <div>
            {isLoadingLive || isFetchingLive ? (
              <div className="py-20 text-center space-y-4">
                <div className="inline-block p-4 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 animate-spin text-indigo-400">
                  <RefreshCw size={28} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Scanning Freelance Platforms Live...</h3>
                  <p className="text-xs text-slate-400 mt-1">Mining active projects, extracting budgets, and crafting tailored proposals.</p>
                </div>
              </div>
            ) : jobsList.length === 0 ? (
              <div className="py-20 text-center rounded-2xl border border-white/10 bg-white/2 p-8 space-y-4">
                <div className="inline-block p-3 rounded-xl bg-white/5 text-slate-400">
                  <Briefcase size={32} />
                </div>
                <h3 className="text-base font-bold text-white">No active jobs found for &ldquo;{activeQuery}&rdquo;</h3>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  Try broadening your search term or click one of the quick niches above (e.g. &ldquo;Shopify Store&rdquo; or &ldquo;WordPress website&rdquo;).
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                {jobsList.map((job) => {
                  const isSaved = savedIds.has(job.id);
                  const isCopied = copiedId === job.id;

                  const platformColor =
                    job.platform === 'upwork'
                      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                      : job.platform === 'fiverr'
                      ? 'bg-teal-500/15 text-teal-300 border-teal-500/30'
                      : 'bg-sky-500/15 text-sky-300 border-sky-500/30';

                  return (
                    <motion.div
                      key={job.id}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="rounded-2xl border border-white/10 bg-[#0e0e22]/70 backdrop-blur-xl p-5 flex flex-col justify-between hover:border-indigo-500/40 hover:shadow-2xl transition-all group"
                    >
                      <div className="space-y-4">
                        {/* Header: Platform & Budget */}
                        <div className="flex items-center justify-between gap-2">
                          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold border ${platformColor}`}>
                            <span className="w-1.5 h-1.5 rounded-full bg-current" />
                            {job.platform_name || job.platform.toUpperCase()}
                          </span>

                          {job.budget ? (
                            <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-300 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/25">
                              <DollarSign size={12} className="-mr-0.5" />
                              {job.budget}
                            </span>
                          ) : (
                            <span className="text-[11px] text-slate-500 font-medium">Budget: Flexible / TBD</span>
                          )}
                        </div>

                        {/* Title */}
                        <div>
                          <h3 className="font-bold text-white text-base leading-snug line-clamp-2 group-hover:text-indigo-300 transition-colors">
                            {job.title}
                          </h3>
                          <p className="text-xs text-slate-400 mt-2 line-clamp-3 leading-relaxed">
                            {job.description}
                          </p>
                        </div>

                        {/* Proposal Preview Box */}
                        <div className="rounded-xl bg-black/40 border border-white/5 p-3.5 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1">
                              <Sparkles size={11} className="text-amber-400" /> Tailored Proposal
                            </span>
                            <button
                              onClick={() => handleCopyPitch(job.id, job.pitch)}
                              className="text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 cursor-pointer"
                            >
                              {isCopied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                              <span>{isCopied ? 'Copied!' : 'Copy'}</span>
                            </button>
                          </div>
                          <p className="text-[11px] text-slate-300 leading-relaxed font-sans line-clamp-3 italic">
                            &ldquo;{job.pitch}&rdquo;
                          </p>
                        </div>
                      </div>

                      {/* Action Buttons */}
                      <div className="pt-4 mt-4 border-t border-white/5 space-y-2">
                        <div className="flex items-center gap-2">
                          {/* 1-Click Open Job & Apply */}
                          <a
                            href={job.project_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex-1 flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 transition-all shadow-md cursor-pointer"
                          >
                            <span>💼 Open Job Post</span>
                            <ArrowUpRight size={13} />
                          </a>

                          {/* Copy Pitch Button */}
                          <button
                            onClick={() => handleCopyPitch(job.id, job.pitch)}
                            className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 hover:text-white transition-all cursor-pointer"
                            title="Copy Proposal Pitch"
                          >
                            {isCopied ? <Check size={15} className="text-emerald-400" /> : <Copy size={15} />}
                          </button>

                          {/* Save to CRM Pipeline Button */}
                          <button
                            onClick={() => saveMutation.mutate(job)}
                            disabled={isSaved || saveMutation.isPending}
                            className={`p-2.5 rounded-xl border transition-all cursor-pointer ${
                              isSaved
                                ? 'bg-purple-500/20 border-purple-500/40 text-purple-300'
                                : 'bg-white/5 hover:bg-white/10 border-white/10 text-slate-300 hover:text-white'
                            }`}
                            title={isSaved ? 'Saved in CRM Pipeline' : 'Save Lead & Create Deal in CRM'}
                          >
                            <Bookmark size={15} className={isSaved ? 'fill-current' : ''} />
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          /* ── Saved Leads in CRM Tab ── */
          <div>
            {isLoadingSaved ? (
              <div className="py-20 text-center space-y-3">
                <RefreshCw size={24} className="animate-spin text-indigo-400 mx-auto" />
                <p className="text-xs text-slate-400">Loading saved CRM projects...</p>
              </div>
            ) : !savedData?.items || savedData.items.length === 0 ? (
              <div className="py-20 text-center rounded-2xl border border-white/10 bg-white/2 p-8 space-y-3">
                <Bookmark size={32} className="text-slate-500 mx-auto" />
                <h3 className="text-base font-bold text-white">No freelance projects saved yet</h3>
                <p className="text-xs text-slate-400 max-w-sm mx-auto">
                  Browse the &ldquo;Live Opportunities&rdquo; tab and click the bookmark icon on any job to save it straight to your CRM sales pipeline.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                {savedData.items.map((b: any) => (
                  <div
                    key={b.id}
                    className="rounded-2xl border border-white/10 bg-[#0e0e22]/70 p-5 flex flex-col justify-between space-y-4 shadow-xl"
                  >
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 capitalize">
                          💼 {b.source} Project
                        </span>
                        {b.budget && (
                          <span className="text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                            {b.budget}
                          </span>
                        )}
                      </div>
                      <h3 className="font-bold text-white text-base leading-snug">{b.name}</h3>
                      {b.description && (
                        <p className="text-xs text-slate-400 line-clamp-3 leading-relaxed">{b.description}</p>
                      )}
                      {b.pitch && (
                        <div className="bg-black/30 p-3 rounded-xl border border-white/5 space-y-1.5">
                          <div className="flex items-center justify-between text-[10px] text-slate-400 font-bold uppercase">
                            <span>Tailored Proposal</span>
                            <button
                              onClick={() => handleCopyPitch(b.id, b.pitch)}
                              className="text-indigo-400 hover:text-indigo-300 font-semibold cursor-pointer"
                            >
                              {copiedId === b.id ? '✓ Copied' : 'Copy'}
                            </button>
                          </div>
                          <p className="text-[11px] text-slate-300 italic line-clamp-3">&ldquo;{b.pitch}&rdquo;</p>
                        </div>
                      )}
                    </div>
                    {b.source_url && (
                      <a
                        href={b.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-500 transition-all cursor-pointer"
                      >
                        <span>Open Application Link</span>
                        <ArrowUpRight size={13} />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
  );
}
