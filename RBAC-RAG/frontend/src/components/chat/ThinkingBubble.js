import React from 'react';
import { Shield } from 'lucide-react';

export function ThinkingBubble() {
  return (
    <div className="mr-auto max-w-[92%] sm:max-w-[70%] rounded-2xl border border-white/10 bg-[rgba(15,23,42,0.72)] px-4 py-3">
      <div className="flex items-center gap-2">
        <Shield className="w-3.5 h-3.5 text-cyan-300" strokeWidth={1.5} />
        <span className="mono-label text-cyan-300">Retrieving · filtering · generating</span>
        <span className="flex gap-1 ml-2">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-300 animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-300 animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-300 animate-bounce" style={{ animationDelay: '300ms' }} />
        </span>
      </div>
    </div>
  );
}
