import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MailCheck, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AuthShell } from './Login';

export default function AuthCallback() {
  const navigate = useNavigate();

  // Automatically go to login after 3 seconds.
  useEffect(() => {
    const t = setTimeout(() => navigate('/login', { replace: true }), 3000);
    return () => clearTimeout(t);
  }, [navigate]);

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
