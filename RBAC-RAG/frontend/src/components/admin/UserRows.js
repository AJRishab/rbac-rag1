import React, { useState } from 'react';
import { toast } from 'sonner';
import { CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { RoleBadge } from '@/components/RoleBadge';
import { api } from '@/lib/api';
import { ADMIN } from '@/constants/testIds';

const ROLES = ['employee', 'manager', 'hr', 'admin'];

export function PendingUserRow({ user, onApproved }) {
  const [role, setRole] = useState('employee');
  const [submitting, setSubmitting] = useState(false);

  const approve = async () => {
    setSubmitting(true);
    try {
      await api.post(`/admin/users/${user.id}/approve`, { role });
      toast.success(`Approved ${user.email} as ${role}`);
      if (onApproved) onApproved();
    } catch (err) {
      console.error('[admin] approve failed', err);
      toast.error('Approval failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div data-testid={ADMIN.pendingUserRow} className="px-3 sm:px-4 py-3 flex flex-col gap-3">
      <div className="min-w-0">
        <div className="text-sm text-slate-100 break-all">{user.email}</div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] font-mono text-slate-500">
          <span>registered {new Date(user.created_at).toLocaleDateString()}</span>
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/25 bg-amber-500/10 px-2 py-0.5 text-amber-200 text-[10px] font-mono">pending</span>
        </div>
      </div>
      <div className="flex flex-col min-[400px]:flex-row items-stretch min-[400px]:items-center gap-2">
        <Select value={role} onValueChange={setRole}>
          <SelectTrigger data-testid={ADMIN.pendingUserRoleSelect} className="w-full min-[400px]:w-36 bg-black/30 border-white/15 text-slate-100 focus:ring-cyan-400/40 focus:ring-offset-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-[hsl(var(--card))] border-white/10">
            {ROLES.map((r) => (
              <SelectItem key={r} value={r} className="font-mono uppercase text-xs">{r}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          data-testid={ADMIN.pendingUserApproveButton}
          onClick={approve}
          disabled={submitting}
          className="w-full min-[400px]:w-auto bg-cyan-500 text-slate-900 hover:bg-cyan-400 font-medium"
        >
          <CheckCircle2 className="w-4 h-4 mr-1" strokeWidth={2} />
          Approve
        </Button>
      </div>
    </div>
  );
}

export function ApprovedUserRow({ user, onChanged }) {
  const [role, setRole] = useState(user.role);
  const [saving, setSaving] = useState(false);

  const save = async (newRole) => {
    setRole(newRole);
    setSaving(true);
    try {
      await api.post(`/admin/users/${user.id}/role`, { role: newRole });
      toast.success(`${user.email} → ${newRole}`);
      if (onChanged) onChanged();
    } catch (err) {
      console.error('[admin] role change failed', err);
      toast.error('Failed to update role');
      setRole(user.role);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid={ADMIN.approvedUserRow} className="px-3 sm:px-4 py-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="flex-1 min-w-0">
        <div className="text-sm text-slate-100 break-all">{user.email}</div>
        <div className="mt-0.5 text-[10px] font-mono text-slate-500">created {new Date(user.created_at).toLocaleDateString()}</div>
      </div>
      <div className="flex items-center gap-2 min-w-0">
        <RoleBadge role={role} className="shrink-0" />
        <Select value={role} onValueChange={save} disabled={saving}>
          <SelectTrigger data-testid={ADMIN.approvedUserRoleSelect} className="flex-1 sm:flex-none sm:w-36 bg-black/30 border-white/15 text-slate-100 focus:ring-cyan-400/40 focus:ring-offset-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-[hsl(var(--card))] border-white/10">
            {ROLES.map((r) => (
              <SelectItem key={r} value={r} className="font-mono uppercase text-xs">{r}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
