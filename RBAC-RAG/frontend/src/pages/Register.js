import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AuthShell, FormField } from './Login';
import { useAuth } from '@/contexts/AuthContext';
import { AUTH } from '@/constants/testIds';

export default function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const { register } = useAuth();
  const navigate = useNavigate();

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) return setError('Password must be at least 8 characters');
    if (password !== confirm) return setError('Passwords do not match');
    setSubmitting(true);
    try {
      await register(email.trim(), password);
      toast.success('Account created — check your email to verify it');
      navigate('/verify-email', { replace: true, state: { email: email.trim() } });
    } catch (err) {
      const msg = err?.message || err?.response?.data?.detail || 'Registration failed';
      setError(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell title="Create your account" subtitle="An admin will approve your account and assign your role.">
      <form onSubmit={onSubmit} className="space-y-4">
        <FormField label="Email">
          <Input
            data-testid={AUTH.emailInput}
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="you@company.com"
            className="bg-black/30 border-white/15 text-slate-100 placeholder:text-slate-500 focus-visible:ring-cyan-400/40 focus-visible:ring-offset-0"
          />
        </FormField>
        <FormField label="Password">
          <Input
            data-testid={AUTH.passwordInput}
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            placeholder="At least 8 characters"
            className="bg-black/30 border-white/15 text-slate-100 placeholder:text-slate-500 focus-visible:ring-cyan-400/40 focus-visible:ring-offset-0"
          />
        </FormField>
        <FormField label="Confirm password">
          <Input
            data-testid={AUTH.confirmPasswordInput}
            type="password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            placeholder="••••••••"
            className="bg-black/30 border-white/15 text-slate-100 placeholder:text-slate-500 focus-visible:ring-cyan-400/40 focus-visible:ring-offset-0"
          />
        </FormField>

        {error && (
          <div data-testid={AUTH.errorMessage} className="rounded-md border border-red-400/25 bg-red-500/8 px-3 py-2 text-xs text-red-200 font-mono">
            {error}
          </div>
        )}

        <Button
          type="submit"
          data-testid={AUTH.submitButton}
          disabled={submitting}
          className="w-full bg-cyan-500 text-slate-900 hover:bg-cyan-400 shadow-[0_0_0_1px_rgba(34,211,238,0.35),0_0_28px_rgba(34,211,238,0.18)] font-medium disabled:opacity-60"
        >
          {submitting ? 'Creating account…' : (<>Create account <UserPlus className="w-4 h-4 ml-1" strokeWidth={1.75} /></>)}
        </Button>

        <div className="pt-2 text-center text-sm text-slate-400">
          Already have an account?{' '}
          <Link data-testid={AUTH.switchToLogin} to="/login" className="text-cyan-300 hover:text-cyan-200 underline underline-offset-4 decoration-cyan-400/30">
            Sign in
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}
