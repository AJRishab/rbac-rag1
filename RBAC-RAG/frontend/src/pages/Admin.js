import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ChevronLeft, Users, Database, KeyRound, LogOut } from 'lucide-react';
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
    <div className="app-shell text-slate-100 overflow-x-hidden">
      <div className="sticky top-0 z-20 h-14 border-b border-white/8 backdrop-blur-md bg-[hsl(var(--background))]/80 flex items-center justify-between gap-2 px-2 sm:px-6">
        <div className="flex items-center gap-1.5 sm:gap-3 min-w-0">
          <Button
            data-testid={ADMIN.backToChatButton}
            variant="ghost"
            size="sm"
            onClick={() => navigate('/chat')}
            className="text-slate-300 hover:bg-white/5 px-2 sm:px-3 shrink-0"
          >
            <ChevronLeft className="w-4 h-4 sm:mr-1" strokeWidth={1.75} />
            <span className="hidden sm:inline">Chat</span>
          </Button>
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-md bg-cyan-500/15 border border-cyan-400/30 flex items-center justify-center shrink-0">
              <KeyRound className="w-4 h-4 text-cyan-300" strokeWidth={1.75} />
            </div>
            <span className="font-display font-bold text-base sm:text-lg truncate">
              Admin <span className="text-cyan-300 hidden min-[360px]:inline">console</span>
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1 sm:gap-3 shrink-0">
          <div className="flex items-center gap-1.5 sm:gap-2 border border-white/10 bg-white/[0.03] px-1.5 sm:px-2 py-1 rounded-full max-w-[42vw] sm:max-w-none">
            <span className="font-mono text-[10px] sm:text-[11px] text-slate-200 truncate hidden min-[400px]:inline max-w-[7rem] sm:max-w-[180px]">
              {user?.email}
            </span>
            <RoleBadge role={user?.role} />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { logout(); navigate('/login'); }}
            className="text-slate-300 hover:bg-white/5 px-2 sm:px-3"
          >
            <LogOut className="w-3.5 h-3.5 sm:mr-1" strokeWidth={1.75} />
            <span className="hidden sm:inline">Sign out</span>
          </Button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-6 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
        <Tabs value={tab} onValueChange={setTab} className="space-y-4 sm:space-y-6">
          <TabsList className="bg-black/30 border border-white/10 p-1 w-full sm:w-auto grid grid-cols-2 sm:inline-flex h-auto">
            <TabsTrigger
              data-testid={ADMIN.usersTab}
              value="users"
              className="data-[state=active]:bg-cyan-500/12 data-[state=active]:text-cyan-100 data-[state=active]:shadow-[0_0_0_1px_rgba(34,211,238,0.25)] text-slate-300 gap-1.5 py-2.5"
            >
              <Users className="w-3.5 h-3.5" strokeWidth={1.75} />
              Users
            </TabsTrigger>
            <TabsTrigger
              data-testid={ADMIN.documentsTab}
              value="documents"
              className="data-[state=active]:bg-cyan-500/12 data-[state=active]:text-cyan-100 data-[state=active]:shadow-[0_0_0_1px_rgba(34,211,238,0.25)] text-slate-300 gap-1.5 py-2.5"
            >
              <Database className="w-3.5 h-3.5" strokeWidth={1.75} />
              Documents
            </TabsTrigger>
          </TabsList>

          <TabsContent value="users" className="space-y-4 sm:space-y-6 mt-0">
            <UsersPanel />
          </TabsContent>
          <TabsContent value="documents" className="space-y-4 sm:space-y-6 mt-0">
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
    <div className="grid gap-4 sm:gap-6">
      <div className="panel overflow-hidden">
        <div className="px-3 sm:px-4 py-3 border-b border-white/10 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="mono-label text-amber-300 truncate">Pending approvals</span>
            <span className="text-xs font-mono text-slate-500 shrink-0">({pending.length})</span>
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

      <div className="panel overflow-hidden">
        <div className="px-3 sm:px-4 py-3 border-b border-white/10 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="mono-label text-emerald-300 truncate">Approved users</span>
            <span className="text-xs font-mono text-slate-500 shrink-0">({approved.length})</span>
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
    <div className="grid gap-4 sm:gap-6">
      <UploadCard onUploaded={load} />

      <div className="panel overflow-hidden">
        <div className="px-3 sm:px-4 py-3 border-b border-white/10 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="mono-label text-cyan-300 truncate">Knowledge base</span>
            <span className="text-xs font-mono text-slate-500 shrink-0">({docs.length})</span>
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
