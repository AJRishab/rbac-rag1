import React from 'react';
import { cn } from '@/lib/utils';
import { CitationChip } from '@/components/CitationChip';
import { RetrievalDetailPanel } from '@/components/RetrievalDetailPanel';
import { CHAT } from '@/constants/testIds';
import { Shield } from 'lucide-react';

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (_) { return ''; }
}

export function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const citations = (message.citations || []).filter(Boolean);

  return (
    <div className={cn('flex w-full', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          isUser
            ? 'ml-auto max-w-[92%] sm:max-w-[75%] rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3'
            : 'mr-auto max-w-[92%] sm:max-w-[82%] rounded-2xl border border-white/10 bg-[rgba(15,23,42,0.72)] px-4 py-3 shadow-[0_0_0_1px_rgba(148,163,184,0.06)]'
        )}
        data-testid={isUser ? CHAT.messageBubbleUser : CHAT.messageBubbleAssistant}
      >
        {!isUser && (
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-flex items-center gap-1.5 text-[10px] font-mono tracking-[0.15em] uppercase text-cyan-300">
              <Shield className="w-3 h-3" strokeWidth={1.5} />
              Sentry
            </span>
            <span className="text-[10px] font-mono text-slate-500">{formatTime(message.created_at)}</span>
          </div>
        )}
        <div className={isUser ? 'text-sm text-slate-100 whitespace-pre-wrap' : 'answer-prose whitespace-pre-wrap'}>
          {message.content}
        </div>

        {!isUser && citations.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {citations.map((c, i) => (
              <CitationChip key={`${c.title}-${i}`} citation={c} index={i} />
            ))}
          </div>
        )}

        {!isUser && message.retrieval_detail && <RetrievalDetailPanel message={message} />}

        {isUser && (
          <div className="mt-1 text-[10px] font-mono text-slate-500 text-right">
            {formatTime(message.created_at)}
          </div>
        )}
      </div>
    </div>
  );
}
