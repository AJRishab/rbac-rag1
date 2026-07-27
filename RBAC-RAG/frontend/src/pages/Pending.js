import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Clock, Shield, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AuthShell } from './Login';
import { AUTH } from '@/constants/testIds';

export default function Pending() {
  const location = useLocation();
  const email = location.state?.email || 'your account';

  return (
    <AuthShell title="Awaiting approval" subtitle="Your account has been created.">
      <div className="space-y-5">
        <div className="rounded-lg border border-amber-400/25 bg-amber-500/8 p-4 flex items-start gap-3">
          <div className="w-8 h-8 rounded-md bg-amber-500/15 border border-amber-400/30 flex items-center justify-center shrink-0">
            <Clock className="w-4 h-4 text-amber-300" strokeWidth={1.75} />
          </div>
          <div>
            <div className="mono-label text-amber-300 mb-1">status=pending</div>
            <p className="text-sm text-slate-100 leading-relaxed">
              An administrator needs to approve <span className="font-mono text-amber-200">{email}</span> and
              assign your role before you can sign in.
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-white/8 bg-black/25 p-4">
          <div className="mono-label text-slate-400 mb-2">What happens next</div>
          <ul className="space-y-2 text-sm text-slate-300">
            <li className="flex items-start gap-2"><Shield className="w-3.5 h-3.5 text-cyan-300 mt-0.5" /> Admin approves your account and assigns a role.</li>
            <li className="flex items-start gap-2"><Shield className="w-3.5 h-3.5 text-cyan-300 mt-0.5" /> You return here and sign in.</li>
            <li className="flex items-start gap-2"><Shield className="w-3.5 h-3.5 text-cyan-300 mt-0.5" /> Every answer you get respects the role assigned to you.</li>
          </ul>
        </div>

        <Link to="/login">
          <Button
            data-testid={AUTH.pendingBackToLogin}
            variant="outline"
            className="w-full border-white/20 bg-transparent hover:bg-white/[0.04] text-slate-100"
          >
            Back to sign in
            <ArrowRight className="w-4 h-4 ml-1" strokeWidth={1.75} />
          </Button>
        </Link>
      </div>
    </AuthShell>
  );
}
