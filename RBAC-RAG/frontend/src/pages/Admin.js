import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ChevronLeft, Users, Database, KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { RoleBadge } from '@/components/RoleBadge';
import { PendingUserRow, ApprovedUserRow } from '@/components/admin/UserRows';
import { UploadCard } from '@/components/admin/UploadCard';
import { DocumentRow } from '@/components/admin/DocumentRow';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';
import { ADMIN } from '@/constants/testIds';

export default function Admin() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('users');

  return (
    <div className="app-shell min-h-screen text-slate-100">
      <div className="h-14 border-b border-white/8 backdrop-blur-md bg-[hsl(var(--background))]/60 flex items-center justify-between px-3 sm:px-6">
        <div className="flex items-center gap-3">
          <Button
            data-testid={ADMIN.backToChatButton}
            variant="ghost"
            size="sm"
            onClick={() => navigate('/chat')}
            className="text-slate-300 hover:bg-white/5"
          >
            <ChevronLeft className="w-4 h-4 mr-1" strokeWidth={1.75} />
            Chat
          </Button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-cyan-500/15 border border-cyan-400/30 flex items-center justify-center">
              <KeyRound className="w-4 h-4 text-cyan-300" strokeWidth={1.75} />
            </div>
            <span className="font-display font-bold text-lg">Admin <span className="text-cyan-300">console</span></span>
          </div>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-2 border border-white/10 bg-white/[0.03] px-2 py-1 rounded-full">
            <span className="font-mono text-[11px] text-slate-200 max-w-[180px] truncate">{user?.email}</span>
            <RoleBadge role={user?.role} />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { logout(); navigate('/login'); }}
            className="text-slate-300 hover:bg-white/5"
          >
            Sign out
          </Button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <Tabs value={tab} onValueChange={setTab} className="space-y-6">
          <TabsList className="bg-black/30 border border-white/10 p-1">
            <TabsTrigger
              data-testid={ADMIN.usersTab}
              value="users"
              className="data-[state=active]:bg-cyan-500/12 data-[state=active]:text-cyan-100 data-[state=active]:shadow-[0_0_0_1px_rgba(34,211,238,0.25)] text-slate-300 gap-1.5"
            >
              <Users className="w-3.5 h-3.5" strokeWidth={1.75} />
              Users
            </TabsTrigger>
            <TabsTrigger
              data-testid={ADMIN.documentsTab}
              value="documents"
              className="data-[state=active]:bg-cyan-500/12 data-[state=active]:text-cyan-100 data-[state=active]:shadow-[0_0_0_1px_rgba(34,211,238,0.25)] text-slate-300 gap-1.5"
            >
              <Database className="w-3.5 h-3.5" strokeWidth={1.75} />
              Documents
            </TabsTrigger>
          </TabsList>

          <TabsContent value="users" className="space-y-6">
            <UsersPanel />
          </TabsContent>
          <TabsContent value="documents" className="space-y-6">
            <DocumentsPanel />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function UsersPanel() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/admin/users');
      setUsers(data);
    } catch (err) {
      console.error('[admin] list users failed', err);
      toast.error('Failed to load users');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const pending = users.filter((u) => u.status !== 'approved');
  const approved = users.filter((u) => u.status === 'approved');

  return (
    <div className="grid gap-6">
      <div className="panel">
        <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="mono-label text-amber-300">Pending approvals</span>
            <span className="text-xs font-mono text-slate-500">({pending.length})</span>
          </div>
        </div>
        <div className="divide-y divide-white/6">
          {loading ? (
            <div className="px-4 py-6 text-sm text-slate-500 font-mono">Loading…</div>
          ) : pending.length === 0 ? (
            <div className="px-4 py-6 text-sm text-slate-500 font-mono">No pending users.</div>
          ) : pending.map((u) => (
            <PendingUserRow key={u.id} user={u} onApproved={load} />
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="mono-label text-emerald-300">Approved users</span>
            <span className="text-xs font-mono text-slate-500">({approved.length})</span>
          </div>
        </div>
        <div className="divide-y divide-white/6">
          {approved.map((u) => (
            <ApprovedUserRow key={u.id} user={u} onChanged={load} />
          ))}
        </div>
      </div>
    </div>
  );
}

function DocumentsPanel() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/admin/documents');
      setDocs(data);
    } catch (err) {
      console.error('[admin] list documents failed', err);
      toast.error('Failed to load documents');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="grid gap-6">
      <UploadCard onUploaded={load} />

      <div className="panel">
        <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="mono-label text-cyan-300">Knowledge base</span>
            <span className="text-xs font-mono text-slate-500">({docs.length})</span>
          </div>
        </div>
        <div className="divide-y divide-white/6">
          {loading ? (
            <div className="px-4 py-6 text-sm text-slate-500 font-mono">Loading…</div>
          ) : docs.length === 0 ? (
            <div className="px-4 py-6 text-sm text-slate-500 font-mono">No documents uploaded yet.</div>
          ) : docs.map((d) => (
            <DocumentRow key={d.id} doc={d} onChanged={load} />
          ))}
        </div>
      </div>
    </div>
  );
}
