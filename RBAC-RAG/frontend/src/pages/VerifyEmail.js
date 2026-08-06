import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { MailCheck, ArrowRight, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AuthShell } from './Login';
import { useAuth } from '@/contexts/AuthContext';

export default function VerifyEmail() {
  const navigate = useNavigate();
  const location = useLocation();
  const email = location.state?.email;
  const { resendVerification } = useAuth();
  const [sending, setSending] = useState(false);

  const onResend = async () => {
    if (!email) {
      return toast.error('No email on file — please re-register');
    }
    setSending(true);
    try {
      await resendVerification(email);
      toast.success('Verification email sent — check your inbox');
    } catch (err) {
      toast.error(err?.message || 'Could not resend verification email');
    } finally {
      setSending(false);
    }
  };

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
          {email && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onResend}
              disabled={sending}
              className="mt-3 w-full text-cyan-200 hover:bg-white/5 disabled:opacity-60"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" strokeWidth={1.75} />
              {sending ? 'Sending…' : 'Didn&rsquo;t get it? Resend verification link'}
            </Button>
          )}
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
