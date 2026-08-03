import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { KeyRound, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AuthShell, FormField } from './Login';
import { useAuth } from '@/contexts/AuthContext';
import { AUTH } from '@/constants/testIds';

export default function ChangePassword() {
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const { changePassword, user, logout } = useAuth();
  const navigate = useNavigate();

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (newPassword.length < 8) return setError('New password must be at least 8 characters');
    if (newPassword !== confirm) return setError('Passwords do not match');
    setSubmitting(true);
    try {
      const u = await changePassword(newPassword);
      toast.success('Password updated');
      if (u.status !== 'approved') navigate('/pending', { replace: true });
      else navigate('/chat', { replace: true });
    } catch (err) {
      const msg = err?.message || err?.response?.data?.detail || 'Failed to change password';
      setError(typeof msg === 'string' ? msg : 'Failed to change password');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell title="Change your password" subtitle="Set a new password for your account.">
      <div className="rounded-lg border border-amber-400/25 bg-amber-500/8 p-3 mb-5 flex items-start gap-2">
        <ShieldAlert className="w-4 h-4 text-amber-300 mt-0.5 shrink-0" strokeWidth={1.75} />
        <p className="text-xs text-amber-100">Your account has a temporary password. Please set a new one before continuing.</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <FormField label="New password">
          <Input
            data-testid={AUTH.changePasswordNew}
            type="password"
            required
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
            placeholder="At least 8 characters"
            className="bg-black/30 border-white/15 text-slate-100 focus-visible:ring-cyan-400/40 focus-visible:ring-offset-0"
          />
        </FormField>
        <FormField label="Confirm new password">
          <Input
            data-testid={AUTH.changePasswordConfirm}
            type="password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            className="bg-black/30 border-white/15 text-slate-100 focus-visible:ring-cyan-400/40 focus-visible:ring-offset-0"
          />
        </FormField>

        {error && (
          <div data-testid={AUTH.errorMessage} className="rounded-md border border-red-400/25 bg-red-500/8 px-3 py-2 text-xs text-red-200 font-mono">
            {error}
          </div>
        )}

        <div className="flex items-center gap-2">
          <Button
            type="submit"
            data-testid={AUTH.changePasswordSubmit}
            disabled={submitting}
            className="flex-1 bg-cyan-500 text-slate-900 hover:bg-cyan-400 font-medium disabled:opacity-60"
          >
            {submitting ? 'Updating…' : (<>Update password <KeyRound className="w-4 h-4 ml-1" strokeWidth={1.75} /></>)}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => { logout(); navigate('/login', { replace: true }); }}
            className="border-white/20 bg-transparent hover:bg-white/[0.04] text-slate-100"
          >
            Sign out
          </Button>
        </div>
      </form>
    </AuthShell>
  );
}
