import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { Shield, ArrowRight, LogIn } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/contexts/AuthContext';
import { AUTH } from '@/constants/testIds';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const u = await login(email.trim(), password);
      toast.success('Signed in');
      if (u.must_change_password) return navigate('/change-password', { replace: true });
      if (u.status !== 'approved') return navigate('/pending', { replace: true });
      const to = location.state?.from?.pathname || '/chat';
      navigate(to, { replace: true });
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Login failed';
      const display = typeof msg === 'string' ? msg : 'Login failed';
      setError(display);
      toast.error(display);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell title="Access console" subtitle="Sign in with your assigned role.">
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
            autoComplete="current-password"
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
          {submitting ? 'Signing in…' : (<>Sign in <LogIn className="w-4 h-4 ml-1" strokeWidth={1.75} /></>)}
        </Button>

        <div className="pt-2 text-center text-sm text-slate-400">
          Don&rsquo;t have an account?{' '}
          <Link data-testid={AUTH.switchToRegister} to="/register" className="text-cyan-300 hover:text-cyan-200 underline underline-offset-4 decoration-cyan-400/30">
            Create one
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}

export function AuthShell({ title, subtitle, children }) {
  return (
    <div className="landing-shell min-h-screen flex flex-col">
      <nav className="border-b border-white/8 backdrop-blur-md bg-[hsl(var(--background))]/60">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-cyan-500/15 border border-cyan-400/30 flex items-center justify-center">
              <Shield className="w-4 h-4 text-cyan-300" strokeWidth={1.75} />
            </div>
            <span className="font-display font-bold text-lg tracking-tight">SENTRY<span className="text-cyan-300">/RAG</span></span>
          </Link>
          <Link to="/" className="text-sm text-slate-400 hover:text-white transition-colors flex items-center gap-1">
            <ArrowRight className="w-3.5 h-3.5 rotate-180" strokeWidth={1.75} />
            Back to home
          </Link>
        </div>
      </nav>

      <div className="flex-1 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <div className="panel p-6 sm:p-8">
            <div className="mb-6">
              <div className="mono-label text-cyan-300 mb-2">// SENTRY/RAG</div>
              <h1 className="font-display font-semibold text-2xl tracking-tight">{title}</h1>
              {subtitle && <p className="text-sm text-slate-400 mt-1">{subtitle}</p>}
            </div>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

export function FormField({ label, children }) {
  return (
    <label className="block">
      <span className="mono-label text-slate-400 mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}
