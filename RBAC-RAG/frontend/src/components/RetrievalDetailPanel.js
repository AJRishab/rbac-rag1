import React, { useState, useMemo } from 'react';
import { ChevronRight, ShieldCheck, ShieldX, FileWarning } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { CHAT } from '@/constants/testIds';
import { cn } from '@/lib/utils';

function rowKey(prefix, r, i) {
  // Prefer stable identity from the payload. Fall back to a positional key
  // only if the server ever omits both document_id and chunk_index.
  const docId = r?.document_id || 'doc';
  const idx = r?.chunk_index ?? i;
  return `${prefix}:${docId}:${idx}`;
}

function sourceLabel(item) {
  return item.source || item.title || 'Unknown source';
}

function chunkMetadata(item) {
  const parts = [];
  if (item.page != null) parts.push(`p. ${item.page}`);
  if (item.chunk_id != null) parts.push(`chunk ID ${item.chunk_id}`);
  else if (item.chunk_index != null) parts.push(`chunk ${item.chunk_index}`);
  return parts.join(' · ');
}

export function RetrievalDetailPanel({ message }) {
  const [open, setOpen] = useState(false);
  const detail = message.retrieval_detail || {};
  const retrieved = useMemo(() => detail.retrieved || [], [detail.retrieved]);
  const blocked = useMemo(() => detail.blocked || [], [detail.blocked]);
  const retrievedCount = message.retrieved_count ?? retrieved.length;
  const blockedCount = message.blocked_count ?? blocked.length;
  const isAdmin = detail.admin_bypass;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mt-3 rounded-xl border border-white/10 bg-black/20 overflow-hidden">
      <CollapsibleTrigger
        asChild
        data-testid={CHAT.retrievalToggle}
      >
        <button
          type="button"
          className="w-full flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between px-3 py-2.5 hover:bg-white/[0.03] transition-colors text-left"
        >
          <div className="flex items-center gap-2 min-w-0">
            <ChevronRight
              className={cn('w-3.5 h-3.5 text-slate-400 transition-transform shrink-0', open && 'rotate-90')}
              strokeWidth={2}
            />
            <span className="mono-label text-slate-300">Retrieval details</span>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap pl-5 sm:pl-0">
            <span
              data-testid={CHAT.retrievedCount}
              className="inline-flex items-center gap-1 rounded-full border border-emerald-400/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] sm:text-[11px] font-mono text-emerald-200"
            >
              <ShieldCheck className="w-3 h-3 shrink-0" />
              {retrievedCount} retrieved
            </span>
            <span
              data-testid={CHAT.blockedCount}
              className={cn(
                'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] sm:text-[11px] font-mono',
                blockedCount > 0
                  ? 'border-red-400/30 bg-red-500/10 text-red-200'
                  : 'border-white/10 bg-white/[0.02] text-slate-400',
              )}
            >
              <ShieldX className="w-3 h-3 shrink-0" />
              {blockedCount} blocked
            </span>
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0">
        <div className="px-3 pb-3 pt-1 grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-white/8 bg-black/25 p-2 min-w-0">
            <div className="mono-label text-emerald-300/80 mb-2 flex items-center gap-2">
              <ShieldCheck className="w-3 h-3" />
              Retrieved chunks
            </div>
            {retrieved.length === 0 ? (
              <div className="text-xs text-slate-500 italic px-1">No chunks retrieved.</div>
            ) : (
              <ul className="space-y-1.5">
                {retrieved.map((r, i) => (
                  <li
                    key={rowKey('r', r, i)}
                    data-testid={CHAT.retrievalRetrievedRow}
                    className="flex items-start gap-2 rounded-md bg-white/[0.02] border border-white/6 px-2 py-1.5 min-w-0"
                  >
                    <span className="font-mono text-[10px] text-emerald-300 mt-0.5 shrink-0">#{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-slate-200 truncate">{sourceLabel(r)}</div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] font-mono text-slate-500">
                        <span>{chunkMetadata(r)}</span>
                        {typeof r.distance === 'number' && (
                          <span title="cosine distance">d={r.distance.toFixed(3)}</span>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-lg border border-white/8 bg-black/25 p-2 min-w-0">
            <div className="mono-label text-red-300/80 mb-2 flex items-center gap-2">
              <ShieldX className="w-3 h-3" />
              Blocked by role filter
            </div>
            {isAdmin ? (
              <div className="text-xs text-cyan-300/80 italic px-1">Admin: RBAC filter bypassed — no chunks blocked.</div>
            ) : blocked.length === 0 ? (
              <div className="text-xs text-slate-500 italic px-1">Nothing blocked for this query.</div>
            ) : (
              <ul className="space-y-1.5">
                {blocked.map((b, i) => (
                  <li
                    key={rowKey('b', b, i)}
                    data-testid={CHAT.retrievalBlockedRow}
                    className="flex items-start gap-2 rounded-md bg-red-500/[0.04] border border-red-400/15 px-2 py-1.5 min-w-0"
                  >
                    <FileWarning className="w-3 h-3 text-red-300 mt-0.5 shrink-0" strokeWidth={1.75} />
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-slate-200 truncate">{sourceLabel(b)}</div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] font-mono text-slate-500">
                        <span>{chunkMetadata(b)}</span>
                        <span className="text-red-300/80">role mismatch</span>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {detail.role && (
          <div className="px-3 pb-2 text-[10px] font-mono text-slate-500 break-all">
            role={detail.role} · top_k={detail.top_k ?? 5}
            {isAdmin ? ' · admin_bypass=true' : ''}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
