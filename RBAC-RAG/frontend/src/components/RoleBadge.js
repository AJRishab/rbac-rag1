import React from 'react';
import { cn } from '@/lib/utils';

const styles = {
  employee: 'bg-slate-900/50 border-slate-400/25 text-slate-200',
  manager: 'bg-sky-950/50 border-sky-400/30 text-sky-200',
  hr: 'bg-emerald-950/40 border-emerald-400/30 text-emerald-200',
  admin: 'bg-cyan-950/40 border-cyan-400/40 text-cyan-100',
};
const dots = {
  employee: 'bg-slate-300',
  manager: 'bg-sky-300',
  hr: 'bg-emerald-300',
  admin: 'bg-cyan-300',
};

export function RoleBadge({ role, className, testId, showDot = true }) {
  if (!role) return null;
  const key = role.toLowerCase();
  return (
    <span
      data-testid={testId}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-mono font-medium tracking-[0.14em] uppercase',
        styles[key] || styles.employee,
        className,
      )}
    >
      {showDot && <span className={cn('inline-block w-1.5 h-1.5 rounded-full', dots[key] || dots.employee)} />}
      {role}
    </span>
  );
}
