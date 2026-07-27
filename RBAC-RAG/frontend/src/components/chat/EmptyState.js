import React from 'react';
import { Sparkles } from 'lucide-react';
import { CHAT } from '@/constants/testIds';

const SUGGESTIONS_BY_ROLE = {
  admin: [
    'What documents are in the knowledge base?',
    'Summarize our HR policies.',
    'What is the compensation structure?',
  ],
  hr: [
    'What is our compensation policy?',
    'How do we handle performance reviews?',
    'What are the vacation policies?',
  ],
  manager: [
    'How do I conduct hiring interviews?',
    'What onboarding materials should I share with my team?',
    'What are the manager-specific policies?',
  ],
  employee: [
    'How many vacation days do I get?',
    'What are our company values?',
    'How do I request time off?',
  ],
};

export function EmptyState({ role }) {
  const suggestions = SUGGESTIONS_BY_ROLE[role] || SUGGESTIONS_BY_ROLE.employee;
  return (
    <div data-testid={CHAT.emptyState} className="panel p-8 sm:p-10">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-lg bg-cyan-500/15 border border-cyan-400/30 flex items-center justify-center shrink-0">
          <Sparkles className="w-5 h-5 text-cyan-300" strokeWidth={1.75} />
        </div>
        <div className="flex-1">
          <div className="mono-label text-cyan-300 mb-1">// Ready</div>
          <h2 className="font-display font-semibold text-2xl tracking-tight">Ask your knowledge base.</h2>
          <p className="text-sm text-slate-400 mt-1 leading-relaxed max-w-xl">
            Every answer is built only from documents your role is allowed to see. Citations and
            retrieval details are attached to every response.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <span key={s} className="text-xs text-slate-300 border border-white/10 bg-white/[0.02] rounded-full px-3 py-1">
                {s}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
