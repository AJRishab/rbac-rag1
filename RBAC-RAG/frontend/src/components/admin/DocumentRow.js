import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { FileText, Trash2, PencilLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { RoleBadge } from '@/components/RoleBadge';
import { RoleChecklist, ROLES } from '@/components/admin/UploadCard';
import { api } from '@/lib/api';
import { ADMIN } from '@/constants/testIds';

function rolesArrayToMap(rolesArr) {
  const map = { employee: false, manager: false, hr: false, admin: false };
  (rolesArr || []).forEach((r) => { map[r] = true; });
  return map;
}

function EditDialog({ doc, open, onOpenChange, onSaved }) {
  const [roles, setRoles] = useState(() => rolesArrayToMap(doc.allowed_roles));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setRoles(rolesArrayToMap(doc.allowed_roles));
  }, [open, doc.allowed_roles]);

  const save = async () => {
    const selected = ROLES.filter((r) => roles[r]);
    if (selected.length === 0) return toast.error('Select at least one role');
    setSaving(true);
    try {
      await api.patch(`/admin/documents/${doc.id}`, { allowed_roles: selected });
      toast.success('Roles updated');
      onOpenChange(false);
      if (onSaved) onSaved();
    } catch (err) {
      console.error('[admin] update roles failed', err);
      toast.error('Failed to update roles');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          data-testid={ADMIN.docListEditButton}
          variant="outline"
          size="sm"
          className="border-white/20 bg-transparent hover:bg-white/[0.04] text-slate-100"
        >
          <PencilLine className="w-3.5 h-3.5 mr-1" strokeWidth={1.75} />
          Edit
        </Button>
      </DialogTrigger>
      <DialogContent className="bg-[hsl(var(--card))] border-white/10 text-slate-100">
        <DialogHeader>
          <DialogTitle className="font-display">Edit access</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="text-sm text-slate-300">{doc.title}</div>
          <RoleChecklist
            roles={roles}
            onToggle={(r) => setRoles((prev) => ({ ...prev, [r]: !prev[r] }))}
            testId={ADMIN.docEditRoleCheckbox}
          />
          <div className="text-[11px] text-slate-500">Updating roles will re-tag all chunks of this document.</div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="border-white/20 bg-transparent text-slate-200">Cancel</Button>
          <Button
            data-testid={ADMIN.docEditSave}
            onClick={save}
            disabled={saving}
            className="bg-cyan-500 text-slate-900 hover:bg-cyan-400 font-medium"
          >
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DocumentMeta({ doc }) {
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 text-sm text-slate-100 min-w-0">
        <FileText className="w-4 h-4 text-cyan-300 shrink-0" strokeWidth={1.75} />
        <span className="truncate font-medium">{doc.title}</span>
        <span className="font-mono text-[10px] text-slate-500 truncate">{doc.filename}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        {(doc.allowed_roles || []).map((r) => <RoleBadge key={r} role={r} />)}
        <span className="text-[10px] font-mono text-slate-500">· {doc.chunk_count} chunks · {new Date(doc.uploaded_at).toLocaleDateString()}</span>
      </div>
    </div>
  );
}

export function DocumentRow({ doc, onChanged }) {
  const [editOpen, setEditOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const del = async () => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete "${doc.title}" and all its chunks?`)) return;
    setDeleting(true);
    try {
      await api.delete(`/admin/documents/${doc.id}`);
      toast.success('Document deleted');
      if (onChanged) onChanged();
    } catch (err) {
      console.error('[admin] delete failed', err);
      toast.error('Failed to delete');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div data-testid={ADMIN.docListRow} className="px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
      <DocumentMeta doc={doc} />
      <div className="flex items-center gap-2">
        <EditDialog doc={doc} open={editOpen} onOpenChange={setEditOpen} onSaved={onChanged} />
        <Button
          data-testid={ADMIN.docListDeleteButton}
          variant="outline"
          size="sm"
          onClick={del}
          disabled={deleting}
          className="border-red-400/25 bg-red-500/5 hover:bg-red-500/10 text-red-200"
        >
          <Trash2 className="w-3.5 h-3.5 mr-1" strokeWidth={1.75} />
          {deleting ? 'Deleting…' : 'Delete'}
        </Button>
      </div>
    </div>
  );
}
