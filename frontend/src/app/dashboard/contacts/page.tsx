'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { contactsApi, type ContactRaw } from '@/lib/api';
import {
  Users,
  Mail,
  Phone,
  Linkedin,
  Plus,
  Search,
  Star,
  ExternalLink,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Globe,
} from 'lucide-react';
import GlassCard from '@/components/ui/GlassCard';
import Badge from '@/components/ui/Badge';
import LoadingSpinner from '@/components/ui/LoadingSpinner';
import EmptyState from '@/components/ui/EmptyState';

const ROLE_COLORS: Record<string, string> = {
  owner: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  manager: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  marketing: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
  technical: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  sales: 'bg-green-500/20 text-green-300 border-green-500/30',
  general: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
  unknown: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

export default function ContactsPage() {
  const [search, setSearch] = useState('');
  const queryClient = useQueryClient();

  const { data: contacts = [], isLoading } = useQuery({
    queryKey: ['contacts'],
    queryFn: () => contactsApi.list({ limit: 200 }),
  });

  const deleteMutation = useMutation({
    mutationFn: contactsApi.delete,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['contacts'] }),
  });

  const filtered = contacts.filter((c) => {
    const q = search.toLowerCase();
    return (
      c.full_name?.toLowerCase().includes(q) ||
      c.email?.toLowerCase().includes(q) ||
      c.title?.toLowerCase().includes(q)
    );
  });

  const stats = {
    total: contacts.length,
    withEmail: contacts.filter((c) => c.email).length,
    verified: contacts.filter((c) => c.email_verified).length,
    primary: contacts.filter((c) => c.is_primary).length,
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Contact Intelligence</h1>
          <p className="text-slate-400 text-sm mt-1">Extracted contacts from discovered businesses</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Contacts', value: stats.total, icon: <Users size={18} />, color: 'text-indigo-400' },
          { label: 'With Email', value: stats.withEmail, icon: <Mail size={18} />, color: 'text-emerald-400' },
          { label: 'Email Verified', value: stats.verified, icon: <CheckCircle2 size={18} />, color: 'text-blue-400' },
          { label: 'Primary Contacts', value: stats.primary, icon: <Star size={18} />, color: 'text-yellow-400' },
        ].map((s) => (
          <GlassCard key={s.label} className="p-4">
            <div className="flex items-center gap-3">
              <div className={`${s.color}`}>{s.icon}</div>
              <div>
                <p className="text-2xl font-bold text-white">{s.value}</p>
                <p className="text-xs text-slate-400">{s.label}</p>
              </div>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Search */}
      <GlassCard className="p-4">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search contacts..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg pl-10 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50"
          />
        </div>
      </GlassCard>

      {/* Contact List */}
      {isLoading ? (
        <div className="flex justify-center py-12"><LoadingSpinner /></div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Users size={40} className="text-slate-600" />}
          title="No contacts yet"
          description="Contacts are extracted automatically when businesses are audited."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((contact) => (
            <motion.div
              key={contact.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <GlassCard className="p-4 hover:border-white/20 transition-colors">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-semibold text-sm">
                      {(contact.full_name || contact.email || '?')[0].toUpperCase()}
                    </div>
                    <div>
                      <p className="font-semibold text-white text-sm">
                        {contact.full_name || 'Unknown'}
                      </p>
                      {contact.title && (
                        <p className="text-xs text-slate-400">{contact.title}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {contact.is_primary && (
                      <Star size={14} className="text-yellow-400 fill-yellow-400" />
                    )}
                    <button
                      onClick={() => deleteMutation.mutate(contact.id)}
                      className="text-slate-500 hover:text-red-400 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                <div className="space-y-2 text-xs">
                  {contact.email && (
                    <div className="flex items-center gap-2 text-slate-300">
                      <Mail size={12} className="text-slate-500 flex-shrink-0" />
                      <span className="truncate">{contact.email}</span>
                      {contact.email_verified && (
                        <CheckCircle2 size={11} className="text-emerald-400 flex-shrink-0" />
                      )}
                    </div>
                  )}
                  {contact.phone && (
                    <div className="flex items-center gap-2 text-slate-300">
                      <Phone size={12} className="text-slate-500 flex-shrink-0" />
                      <span>{contact.phone}</span>
                    </div>
                  )}
                  {contact.linkedin_url && (
                    <div className="flex items-center gap-2 text-slate-300">
                      <Linkedin size={12} className="text-slate-500 flex-shrink-0" />
                      <a
                        href={contact.linkedin_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:underline truncate"
                      >
                        LinkedIn Profile
                      </a>
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between mt-3 pt-3 border-t border-white/5">
                  <span className={`text-xs px-2 py-0.5 rounded-full border font-medium capitalize ${ROLE_COLORS[contact.role] || ROLE_COLORS.unknown}`}>
                    {contact.role}
                  </span>
                  <div className="flex items-center gap-1 text-xs text-slate-500">
                    <span>Score:</span>
                    <span className="text-white font-medium">
                      {Math.round(contact.confidence_score * 100)}%
                    </span>
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
