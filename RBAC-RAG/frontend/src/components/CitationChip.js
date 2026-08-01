import React from 'react';
import { FileText } from 'lucide-react';
import { CHAT } from '@/constants/testIds';

export function CitationChip({ citation, index }) {
  const source = citation.source || citation.title;
  const metadata = [
    citation.page != null ? `p. ${citation.page}` : null,
    citation.chunk_id != null ? `chunk ID ${citation.chunk_id}` : null,
  ].filter(Boolean).join(' · ');
  return (
    <span
      data-testid={CHAT.citationChip}
      className="inline-flex items-center gap-1.5 rounded-full border border-white/12 bg-white/[0.03] px-2.5 py-1 text-xs text-slate-200 hover:bg-cyan-500/10 hover:border-cyan-400/30 transition-colors"
      title={[source, metadata].filter(Boolean).join(' · ')}
    >
      <FileText className="w-3 h-3 text-cyan-300" strokeWidth={1.5} />
      <span className="font-mono text-[10px] text-cyan-300">#{index + 1}</span>
      <span className="truncate max-w-[min(12rem,55vw)] sm:max-w-[240px]">{source}</span>
      {metadata && <span className="font-mono text-[10px] text-slate-400">{metadata}</span>}
    </span>
  );
}
