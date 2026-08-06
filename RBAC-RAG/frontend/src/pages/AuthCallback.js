import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { MailCheck, MailX, ArrowRight, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AuthShell, FormField } from './Login';
import { useAuth } from '@/contexts/AuthContext';

function getUrlError() {
  // Supabase appends error params to the redirect URL on failed verification:
  // .../auth/callback?error_code=otp_expired&error_description=Email+link+is+invalid...
  try {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('error_code') || params.get('error');
    const desc = params.get('error_description');
    return { code, desc };
  } catch {
    return { code: null, desc: null };
  }
}

export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { resendVerification } = useAuth();
  const [resendEmail, setResendEmail] = useState(location.state?.email || '');
  const [sending, setSending] = useState(false);

  const { code, desc } = getUrlError();
  const isError = Boolean(code);

  // Automatically go to login after 3 seconds (only on the success path).
  useEffect(() => {
    if (isError) return;
    const t = setTimeout(() => navigate('/login', { replace: true }), 3000);
    return () => clearTimeout(t);
  }, [navigate, isError]);

  const onResend = async (e) => {
    e.preventDefault();
    if (!resendEmail.trim()) {
      return toast.error('Enter your email address to resend the link');
    }
    setSending(true);
    try {
      await resendVerification(resendEmail.trim());
      toast.success('Verification email sent — check your inbox');
      navigate('/verify-email', { replace: true, state: { email: resendEmail.trim() } });
    } catch (err) {
      toast.error(err?.message || 'Could not resend verification email');
    } finally {
      setSending(false);
    }
  };

  if (isError) {
    return (
      <AuthShell title="Verification link expired" subtitle="That link is no longer valid.">
        <div className="space-y-5">
          <div className="rounded-lg border border-amber-400/25 bg-amber-500/10 p-4 flex items-start gap-3">
            <div className="w-8 h-8 rounded-md bg-amber-500/15 border border-amber-400/30 flex items-center justify-center shrink-0">
              <MailX className="w-4 h-4 text-amber-300" strokeWidth={1.75} />
            </div>
            <div className="min-w-0">
              <div className="mono-label text-amber-300 mb-1">action=link-expired{code ? ` (${code})` : ''}</div>
              <p className="text-sm text-slate-100 leading-relaxed">
                {desc || 'The verification link is invalid or has expired. Request a new one below.'}
              </p>
            </div>
          </div>

          <form onSubmit={onResend} className="space-y-4">
            <FormField label="Email">
              <Input
                type="email"
                required
                value={resendEmail}
                onChange={(e) => setResendEmail(e.target.value)}
                autoComplete="email"
                placeholder="you@company.com"
                className="bg-black/30 border-white/15 text-slate-100 placeholder:text-slate-500 focus-visible:ring-cyan-400/40 focus-visible:ring-offset-0"
              />
            </FormField>
            <Button
              type="submit"
              disabled={sending}
              className="w-full bg-cyan-500 text-slate-900 hover:bg-cyan-400 shadow-[0_0_0_1px_rgba(34,211,238,0.35),0_0_28px_rgba(34,211,238,0.18)] font-medium disabled:opacity-60"
            >
              {sending ? 'Sending…' : (<><RefreshCw className="w-4 h-4 mr-1" strokeWidth={1.75} /> Resend verification link</>)}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => navigate('/login')}
              className="w-full text-slate-300 hover:bg-white/5"
            >
              Back to sign in
              <ArrowRight className="w-4 h-4 ml-1" strokeWidth={1.75} />
            </Button>
          </form>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Email verified successfully!" subtitle="You&rsquo;re all set.">
      <div className="space-y-5">
        <div className="rounded-lg border border-emerald-400/25 bg-emerald-500/10 p-4 flex items-start gap-3">
          <div className="w-8 h-8 rounded-md bg-emerald-500/15 border border-emerald-400/30 flex items-center justify-center shrink-0">
            <MailCheck className="w-4 h-4 text-emerald-300" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <div className="mono-label text-emerald-300 mb-1">email=verified</div>
            <p className="text-sm text-slate-100 leading-relaxed">
              Your email has been verified successfully. Please log in to continue.
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-white/8 bg-black/25 p-4">
          <div className="mono-label text-slate-400 mb-2">Redirecting&hellip;</div>
          <p className="text-sm text-slate-300">
            You&rsquo;ll be taken to the login page in a moment, or use the button below.
          </p>
        </div>

        <Button
          onClick={() => navigate('/login', { replace: true })}
          className="w-full bg-cyan-500 text-slate-900 hover:bg-cyan-400 shadow-[0_0_0_1px_rgba(34,211,238,0.35),0_0_28px_rgba(34,211,238,0.18)] font-medium"
        >
          Go to login
          <ArrowRight className="w-4 h-4 ml-1" strokeWidth={1.75} />
        </Button>
      </div>
    </AuthShell>
  );
}
