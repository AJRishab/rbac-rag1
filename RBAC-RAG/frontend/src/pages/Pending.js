import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, Shield, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AuthShell } from './Login';
import { AUTH } from '@/constants/testIds';
import { useAuth } from '@/contexts/AuthContext';

export default function Pending() {
  const navigate = useNavigate();
  const { logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <AuthShell title="Awaiting Admin Approval" subtitle="Your email has been verified.">
      <div className="space-y-5">
        <div className="rounded-lg border border-amber-400/25 bg-amber-500/8 p-4 flex items-start gap-3">
          <div className="w-8 h-8 rounded-md bg-amber-500/15 border border-amber-400/30 flex items-center justify-center shrink-0">
            <Clock className="w-4 h-4 text-amber-300" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <div className="mono-label text-amber-300 mb-1">status=pending</div>
            <p className="text-sm text-slate-100 leading-relaxed">
              Your email has been verified successfully. Your account is waiting
              for administrator approval.
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-white/8 bg-black/25 p-4">
          <div className="mono-label text-slate-400 mb-2">What happens next</div>
          <ul className="space-y-2 text-sm text-slate-300">
            <li className="flex items-start gap-2">
              <Shield className="w-3.5 h-3.5 text-cyan-300 mt-0.5" strokeWidth={1.75} />
              An admin approves your account and assigns a role.
            </li>
            <li className="flex items-start gap-2">
              <Shield className="w-3.5 h-3.5 text-cyan-300 mt-0.5" strokeWidth={1.75} />
              You return here and sign in.
            </li>
            <li className="flex items-start gap-2">
              <Shield className="w-3.5 h-3.5 text-cyan-300 mt-0.5" strokeWidth={1.75} />
              Every answer you get respects the role assigned to you.
            </li>
          </ul>
        </div>

        <Button
          data-testid={AUTH.pendingBackToLogin}
          onClick={handleLogout}
          variant="outline"
          className="w-full border-white/20 bg-transparent hover:bg-white/[0.04] text-slate-100"
        >
          <LogOut className="w-4 h-4 mr-1" strokeWidth={1.75} />
          Log out
        </Button>
      </div>
    </AuthShell>
  );
}

