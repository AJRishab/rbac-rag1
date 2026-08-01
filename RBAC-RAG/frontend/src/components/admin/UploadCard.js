import React, { useRef, useState } from 'react';
import { toast } from 'sonner';
import { Upload, FileText, X, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { api } from '@/lib/api';
import { ADMIN } from '@/constants/testIds';
import { cn } from '@/lib/utils';

export const ROLES = ['employee', 'manager', 'hr', 'admin'];
const FILE_ACCEPT = '.txt,.md,.markdown,.pdf,.docx';
const FILE_EXT_RE = /\.(txt|md|markdown|pdf|docx)$/i;

function RoleChecklist({ roles, onToggle, testId, availableRoles = ROLES }) {
  return (
    <div className="grid grid-cols-1 min-[380px]:grid-cols-2 sm:grid-cols-4 gap-2">
      {availableRoles.map((r) => (
        <label key={r} className={cn(
          'flex items-center gap-2 rounded-lg border px-3 py-2.5 sm:py-2 cursor-pointer transition-colors touch-manipulation',
          roles[r] ? 'border-cyan-400/40 bg-cyan-500/8' : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.04]',
        )}>
          <Checkbox
            data-testid={testId}
            data-role={r}
            checked={roles[r]}
            onCheckedChange={() => onToggle(r)}
            className="border-white/25 data-[state=checked]:bg-cyan-500 data-[state=checked]:border-cyan-400"
          />
          <span className={cn('font-mono text-xs uppercase tracking-widest', roles[r] ? 'text-cyan-100' : 'text-slate-300')}>{r}</span>
        </label>
      ))}
    </div>
  );
}

function Dropzone({ file, dragOver, onSelectFile, onClearFile, inputRef, onDrop, setDragOver }) {
  return (
    <div
      data-testid={ADMIN.docUploadDropzone}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={cn(
        'cursor-pointer rounded-xl border border-dashed px-3 sm:px-4 py-5 sm:py-6 text-center transition-colors',
        dragOver ? 'border-cyan-400/50 bg-cyan-500/8 shadow-[0_0_0_1px_rgba(34,211,238,0.2)]' : 'border-white/20 bg-white/[0.02] hover:bg-white/[0.04]',
      )}
    >
      <input
        data-testid={ADMIN.docUploadFileInput}
        ref={inputRef}
        type="file"
        accept={FILE_ACCEPT}
        onChange={onSelectFile}
        className="hidden"
      />
      {file ? (
        <div className="flex items-center justify-center gap-2 text-sm text-slate-100 min-w-0 px-1">
          <FileText className="w-4 h-4 text-cyan-300 shrink-0" strokeWidth={1.75} />
          <span className="font-mono truncate min-w-0">{file.name}</span>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onClearFile(); }}
            className="text-slate-400 hover:text-red-300 p-1.5 shrink-0 touch-manipulation"
            aria-label="Clear file"
          >
            <X className="w-4 h-4" strokeWidth={2} />
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          <Upload className="w-5 h-5 text-cyan-300" strokeWidth={1.75} />
          <div className="text-sm text-slate-200">Tap to choose a file</div>
          <div className="text-[10px] font-mono text-slate-500 hidden sm:block">or drop here</div>
          <div className="text-[10px] font-mono text-slate-500">.txt / .md / .pdf / .docx</div>
        </div>
      )}
    </div>
  );
}

export function UploadCard({ onUploaded }) {
  const [title, setTitle] = useState('');
  const [file, setFile] = useState(null);
  const [roles, setRoles] = useState({ employee: true, manager: false, hr: false, admin: true });
  const [submitting, setSubmitting] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const selectedRoles = ROLES.filter((r) => roles[r]);

  const toggleRole = (r) => setRoles((prev) => ({ ...prev, [r]: !prev[r] }));

  const acceptFile = (f) => {
    if (!f) return;
    setFile(f);
    setTitle((prev) => prev || f.name.replace(FILE_EXT_RE, ''));
  };

  const clearFile = () => {
    setFile(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  const onSelectFile = (e) => acceptFile(e.target.files?.[0]);
  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    acceptFile(e.dataTransfer.files?.[0]);
  };

  const submit = async () => {
    if (!file) return toast.error('Select a file to upload');
    if (!title.trim()) return toast.error('Provide a title');
    if (selectedRoles.length === 0) return toast.error('Select at least one role');
    setSubmitting(true);
    const form = new FormData();
    form.append('title', title.trim());
    form.append('allowed_roles', selectedRoles.join(','));
    form.append('file', file);
    try {
      const { data } = await api.post('/admin/documents', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast.success(`Uploaded ${data.title} (${data.chunk_count} chunks)`);
      setTitle('');
      clearFile();
      if (onUploaded) onUploaded();
    } catch (err) {
      console.error('[admin] upload failed', err);
      const msg = err?.response?.data?.detail || 'Upload failed';
      toast.error(typeof msg === 'string' ? msg : 'Upload failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel overflow-hidden">
      <div className="px-3 sm:px-4 py-3 border-b border-white/10 flex flex-col gap-0.5 sm:flex-row sm:items-center sm:justify-between">
        <span className="mono-label text-cyan-300">Upload document</span>
        <span className="text-[10px] font-mono text-slate-500">.txt / .md / .pdf / .docx · max 20 MB</span>
      </div>
      <div className="p-3 sm:p-4 space-y-4">
        <div>
          <span className="mono-label text-slate-400 mb-1 block">Title</span>
          <Input
            data-testid={ADMIN.docUploadTitleInput}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. HR Policy 2026"
            className="bg-black/30 border-white/15 text-slate-100 placeholder:text-slate-500 focus-visible:ring-cyan-400/40 focus-visible:ring-offset-0 text-base sm:text-sm"
          />
        </div>
        <div>
          <span className="mono-label text-slate-400 mb-1 block">File</span>
          <Dropzone
            file={file}
            dragOver={dragOver}
            inputRef={inputRef}
            onSelectFile={onSelectFile}
            onClearFile={clearFile}
            onDrop={onDrop}
            setDragOver={setDragOver}
          />
        </div>
        <div>
          <span className="mono-label text-slate-400 mb-2 block">Allowed roles</span>
          <RoleChecklist roles={roles} onToggle={toggleRole} testId={ADMIN.docUploadRoleCheckbox} />
        </div>
        <div className="pt-1 sm:pt-2 flex sm:justify-end">
          <Button
            data-testid={ADMIN.docUploadSubmit}
            onClick={submit}
            disabled={submitting || !file || selectedRoles.length === 0}
            className="w-full sm:w-auto bg-cyan-500 text-slate-900 hover:bg-cyan-400 font-medium disabled:opacity-60 min-h-11"
          >
            {submitting ? 'Uploading + embedding…' : (<>Upload document <Plus className="w-4 h-4 ml-1" strokeWidth={2} /></>)}
          </Button>
        </div>
      </div>
    </div>
  );
}

export { RoleChecklist };
