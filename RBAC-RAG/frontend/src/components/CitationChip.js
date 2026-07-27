import React from 'react';
import { FileText } from 'lucide-react';
import { CHAT } from '@/constants/testIds';

export function CitationChip({ citation, index }) {
  return (
    <span
      data-testid={CHAT.citationChip}
      className="inline-flex items-center gap-1.5 rounded-full border border-white/12 bg-white/[0.03] px-2.5 py-1 text-xs text-slate-200 hover:bg-cyan-500/10 hover:border-cyan-400/30 transition-colors"
      title={citation.title}
    >
      <FileText className="w-3 h-3 text-cyan-300" strokeWidth={1.5} />
      <span className="font-mono text-[10px] text-cyan-300">#{index + 1}</span>
      <span className="truncate max-w-[240px]">{citation.title}</span>
    </span>
  );
}
