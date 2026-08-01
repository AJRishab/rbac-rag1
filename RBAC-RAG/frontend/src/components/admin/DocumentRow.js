import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CheckCircle2, FileText, RefreshCw, ShieldCheck, Sparkles, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { RoleBadge } from '@/components/RoleBadge';
import { RoleChecklist } from '@/components/admin/UploadCard';
import { api } from '@/lib/api';
import { ADMIN } from '@/constants/testIds';

function rolesArrayToMap(rolesArr) {
  return (rolesArr || []).reduce((map, role) => ({ ...map, [role]: true }), {});
}

function statusBadge(status) {
  const published = status === 'published';
  return (
    <span className={published
      ? 'inline-flex rounded-full border border-emerald-400/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-mono text-emerald-200'
      : 'inline-flex rounded-full border border-amber-400/25 bg-amber-500/10 px-2 py-0.5 text-[10px] font-mono text-amber-200'}
    >
      {published ? 'published' : 'pending review'}
    </span>
  );
}

function ChunkReviewDialog({ doc, open, onOpenChange, onSaved }) {
  const [chunks, setChunks] = useState([]);
  const [changed, setChanged] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/documents/${doc.id}/chunks`);
      setChunks(data);
      setChanged(new Set());
    } catch (err) {
      console.error('[admin] load chunks failed', err);
      toast.error('Failed to load document chunks');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) load();
    // The dialog only reloads when opened or when a different document is selected.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, doc.id]);

  const toggleRole = (chunkId, role) => {
    setChunks((previous) => previous.map((chunk) => {
      if (chunk.id !== chunkId) return chunk;
      const roles = new Set(chunk.allowed_roles);
      if (roles.has(role)) roles.delete(role);
      else roles.add(role);
      return { ...chunk, allowed_roles: [...roles], roles_ai_suggested: false };
    }));
    setChanged((previous) => new Set([...previous, chunkId]));
  };

  const reset = async () => {
    setSaving(true);
    try {
      const { data } = await api.post(`/admin/documents/${doc.id}/reset-chunk-roles`);
      setChunks(data);
      setChanged(new Set());
      toast.success('Chunk roles reset to document defaults');
    } catch (err) {
      console.error('[admin] reset chunks failed', err);
      toast.error('Failed to reset chunk roles');
    } finally {
      setSaving(false);
    }
  };

  const saveAndPublish = async () => {
    const invalid = chunks.some((chunk) => chunk.allowed_roles.length === 0);
    if (invalid) return toast.error('Every chunk needs at least one role');
    setSaving(true);
    try {
      for (const chunk of chunks.filter((item) => changed.has(item.id))) {
        await api.patch(`/admin/documents/${doc.id}/chunks/${chunk.id}`, {
          allowed_roles: chunk.allowed_roles,
        });
      }
      await api.post(`/admin/documents/${doc.id}/publish`);
      toast.success('Chunk tags saved and document published');
      onOpenChange(false);
      if (onSaved) onSaved();
    } catch (err) {
      console.error('[admin] publish chunks failed', err);
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to save and publish');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          data-testid={ADMIN.docReviewButton}
          variant="outline"
          size="sm"
          className="flex-1 sm:flex-none border-cyan-400/30 bg-cyan-500/8 hover:bg-cyan-500/12 text-cyan-100"
        >
          <ShieldCheck className="w-3.5 h-3.5 mr-1" strokeWidth={1.75} />
          Review chunks
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col bg-[hsl(var(--card))] border-white/10 text-slate-100">
        <DialogHeader>
          <DialogTitle className="font-display">Review chunk access</DialogTitle>
          <p className="text-sm text-slate-400 break-words">{doc.title}</p>
        </DialogHeader>
        <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
          {loading ? <div className="py-8 text-sm text-slate-500 font-mono">Loading chunks…</div> : chunks.map((chunk) => (
            <section key={chunk.id} className="rounded-lg border border-white/10 bg-black/20 p-3 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono-label text-slate-400">chunk {chunk.chunk_index + 1}</span>
                {chunk.roles_ai_suggested && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-violet-400/25 bg-violet-500/10 px-2 py-0.5 text-[10px] font-mono text-violet-200">
                    <Sparkles className="w-3 h-3" /> AI-suggested
                  </span>
                )}
              </div>
              <p className="text-xs leading-relaxed text-slate-300 whitespace-pre-wrap max-h-28 overflow-y-auto">{chunk.content}</p>
              <RoleChecklist
                roles={rolesArrayToMap(chunk.allowed_roles)}
                onToggle={(role) => toggleRole(chunk.id, role)}
                testId={ADMIN.chunkRoleCheckbox}
                availableRoles={doc.allowed_roles}
              />
            </section>
          ))}
          {!loading && chunks.length === 0 && <div className="py-8 text-sm text-slate-500">This document has no chunks.</div>}
        </div>
        <DialogFooter className="flex-col-reverse sm:flex-row gap-2 sm:justify-between">
          <Button
            data-testid={ADMIN.chunkResetButton}
            variant="outline"
            onClick={reset}
            disabled={saving || loading}
            className="w-full sm:w-auto border-white/20 bg-transparent text-slate-200"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1" /> Reset to document defaults
          </Button>
          <div className="flex flex-col-reverse sm:flex-row gap-2 w-full sm:w-auto">
            <Button variant="outline" onClick={() => onOpenChange(false)} className="border-white/20 bg-transparent text-slate-200">Cancel</Button>
            <Button
              data-testid={ADMIN.chunkSavePublishButton}
              onClick={saveAndPublish}
              disabled={saving || loading || chunks.length === 0}
              className="bg-cyan-500 text-slate-900 hover:bg-cyan-400 font-medium"
            >
              <CheckCircle2 className="w-4 h-4 mr-1" /> {saving ? 'Saving…' : 'Save & publish'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DocumentMeta({ doc }) {
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-start gap-2 text-sm text-slate-100 min-w-0">
        <FileText className="w-4 h-4 text-cyan-300 shrink-0 mt-0.5" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <div className="font-medium break-words">{doc.title}</div>
          <div className="font-mono text-[10px] text-slate-500 truncate mt-0.5">{doc.filename}</div>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {statusBadge(doc.status)}
        {(doc.allowed_roles || []).map((role) => <RoleBadge key={role} role={role} />)}
        <span className="text-[10px] font-mono text-slate-500">· {doc.chunk_count} chunks · {new Date(doc.uploaded_at).toLocaleDateString()}</span>
      </div>
    </div>
  );
}

export function DocumentRow({ doc, onChanged }) {
  const [reviewOpen, setReviewOpen] = useState(false);
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
    <div data-testid={ADMIN.docListRow} className="px-3 sm:px-4 py-3 flex flex-col gap-3">
      <DocumentMeta doc={doc} />
      <div className="flex items-stretch sm:items-center gap-2">
        <ChunkReviewDialog doc={doc} open={reviewOpen} onOpenChange={setReviewOpen} onSaved={onChanged} />
        <Button
          data-testid={ADMIN.docListDeleteButton}
          variant="outline"
          size="sm"
          onClick={del}
          disabled={deleting}
          className="flex-1 sm:flex-none border-red-400/25 bg-red-500/5 hover:bg-red-500/10 text-red-200"
        >
          <Trash2 className="w-3.5 h-3.5 mr-1" strokeWidth={1.75} />
          {deleting ? 'Deleting…' : 'Delete'}
        </Button>
      </div>
    </div>
  );
}
