import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { MailCheck, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AuthShell } from './Login';

export default function VerifyEmail() {
  const navigate = useNavigate();
  const location = useLocation();
  const email = location.state?.email;

  return (
    <AuthShell title="Confirm your email" subtitle="Almost there — one last step.">
      <div className="space-y-5">
        <div className="rounded-lg border border-cyan-400/25 bg-cyan-500/8 p-4 flex items-start gap-3">
          <div className="w-8 h-8 rounded-md bg-cyan-500/15 border border-cyan-400/30 flex items-center justify-center shrink-0">
            <MailCheck className="w-4 h-4 text-cyan-300" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <div className="mono-label text-cyan-300 mb-1">action=verify-email</div>
            <p className="text-sm text-slate-100 leading-relaxed">
              We&rsquo;ve sent a verification link to your email address. Please
              verify your email before logging in.
            </p>
            {email && (
              <p className="mt-2 text-xs font-mono text-slate-400 break-all">
                → {email}
              </p>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-white/8 bg-black/25 p-4">
          <div className="mono-label text-slate-400 mb-2">What to do next</div>
          <ul className="space-y-2 text-sm text-slate-300">
            <li className="flex items-start gap-2">
              <MailCheck className="w-3.5 h-3.5 text-cyan-300 mt-0.5" strokeWidth={1.75} />
              Check your inbox and click the verification link.
            </li>
            <li className="flex items-start gap-2">
              <MailCheck className="w-3.5 h-3.5 text-cyan-300 mt-0.5" strokeWidth={1.75} />
              Return here and sign in with your email and password.
            </li>
          </ul>
        </div>

        <Button
          onClick={() => navigate('/login')}
          className="w-full bg-cyan-500 text-slate-900 hover:bg-cyan-400 shadow-[0_0_0_1px_rgba(34,211,238,0.35),0_0_28px_rgba(34,211,238,0.18)] font-medium"
        >
          Back to sign in
          <ArrowRight className="w-4 h-4 ml-1" strokeWidth={1.75} />
        </Button>
      </div>
    </AuthShell>
  );
}
