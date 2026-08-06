import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Shield, Database, Radar, Activity, Lock, FileText, ChevronRight, ShieldCheck, ShieldX } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LANDING } from '@/constants/testIds';

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="landing-shell min-h-screen text-slate-100">
      {/* NAV */}
      <nav className="top-nav z-30 backdrop-blur-md bg-[hsl(var(--background))]/60 border-b border-white/8">
        <div className="w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-[var(--navbar-height)] flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-cyan-500/15 border border-cyan-400/30 flex items-center justify-center">
              <Shield className="w-4 h-4 text-cyan-300" strokeWidth={1.75} />
            </div>
            <span className="font-display font-bold text-lg tracking-tight">SENTRY<span className="text-cyan-300">/RAG</span></span>
          </Link>
          <Button
            asChild
            variant="outline"
            size="sm"
            data-testid={LANDING.navDashboard}
            className="border-cyan-400/30 bg-cyan-500/8 hover:bg-cyan-500/12 text-cyan-100"
          >
            <Link to="/chat">Dashboard</Link>
          </Button>
        </div>
      </nav>

      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-24 left-1/4 w-[600px] h-[600px] opacity-30">
            <div className="radar-ring inset-0" />
            <div className="radar-ring" style={{ inset: '10%' }} />
            <div className="radar-ring" style={{ inset: '22%' }} />
            <div className="radar-ring" style={{ inset: '35%' }} />
            <div className="radar-sweep opacity-25" />
          </div>
        </div>

        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-20 lg:pt-24 lg:pb-28">
          <div className="grid lg:grid-cols-[1.15fr_1fr] gap-10 lg:gap-16 items-center">
            <div>
              <div className="mono-label inline-flex items-center gap-2 rounded-full border border-cyan-400/25 bg-cyan-500/8 px-3 py-1 text-cyan-200 mb-6">
                <span className="pulse-dot" style={{ width: 6, height: 6 }} />
                Permission-aware RAG
              </div>
              <h1 className="font-display font-bold text-4xl sm:text-5xl lg:text-6xl tracking-tight leading-[1.05]">
                SENTRY<span className="gradient-text">/RAG.</span>
              </h1>
              <p className="mt-5 max-w-xl text-slate-300 text-base sm:text-lg leading-relaxed">
                Ask your organization&rsquo;s knowledge base a question. Get an answer built only
                from what your role is allowed to see.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Button
                  data-testid={LANDING.heroPrimaryCta}
                  onClick={() => {
                    const el = document.getElementById('features');
                    if (el) el.scrollIntoView({ behavior: 'smooth' });
                  }}
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400 shadow-[0_0_0_1px_rgba(34,211,238,0.35),0_0_28px_rgba(34,211,238,0.18)] font-medium"
                >
                  See how it works
                </Button>
                <Button
                  data-testid={LANDING.heroSecondaryCta}
                  variant="outline"
                  onClick={() => navigate('/login')}
                  className="border-white/20 bg-transparent hover:bg-white/[0.04] text-slate-100"
                >
                  Skip to console
                  <ArrowRight className="w-4 h-4 ml-1" strokeWidth={1.75} />
                </Button>
              </div>
            </div>

            {/* Hero right: mock 'live retrieval' panel */}
            <div className="panel p-4 sm:p-5">
              <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded bg-cyan-500/15 border border-cyan-400/30 flex items-center justify-center">
                    <Radar className="w-3.5 h-3.5 text-cyan-300" strokeWidth={1.75} />
                  </div>
                  <span className="mono-label text-slate-300">Live retrieval</span>
                </div>
                <span className="mono-label text-cyan-300">role=hr</span>
              </div>

              <div className="space-y-3">
                <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                  <div className="mono-label text-slate-400 mb-1">Prompt</div>
                  <div className="text-sm text-slate-100">What&rsquo;s our parental leave policy?</div>
                </div>
                <div className="rounded-lg border border-white/10 bg-[rgba(15,23,42,0.72)] p-3">
                  <div className="mono-label text-cyan-300 mb-1">Answer</div>
                  <div className="text-sm text-slate-100 leading-relaxed">
                    12 weeks paid, with an optional 4 weeks unpaid extension.{' '}
                    <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[10px] font-mono ml-1">
                      <FileText className="w-2.5 h-2.5 text-cyan-300" />
                      HR-Policy-2026 § 4.2
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/25 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-mono text-emerald-200">
                    <ShieldCheck className="w-3 h-3" />
                    4 retrieved
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full border border-red-400/30 bg-red-500/10 px-2 py-0.5 text-[11px] font-mono text-red-200">
                    <ShieldX className="w-3 h-3" />
                    2 blocked
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section id="features" className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
        <div className="mono-label text-cyan-300 mb-3">// Capabilities</div>
        <h2 className="font-display font-semibold text-3xl sm:text-4xl tracking-tight">Built for provable access control.</h2>
        <p className="text-slate-400 mt-3 max-w-2xl">Four capabilities that make SENTRY/RAG different from a general chatbot.</p>

        <div className="mt-10 grid gap-5 sm:grid-cols-2">
          <FeatureCard
            testId={LANDING.featureGrounded}
            icon={FileText}
            iconTint="text-cyan-300"
            title="Ask anything, get grounded answers."
            body="Answers are generated only from your organization's own uploaded documents, with citations back to the source — never from general model knowledge."
          >
            <div className="rounded-lg border border-white/10 bg-black/25 p-3 space-y-2">
              <div className="mono-label text-slate-400">Prompt</div>
              <div className="text-sm text-slate-200">What&rsquo;s our parental leave policy?</div>
              <div className="mono-label text-cyan-300">Answer</div>
              <div className="text-sm text-slate-200">12 weeks paid — HR-Policy-2026, §4.2</div>
            </div>
          </FeatureCard>

          <FeatureCard
            testId={LANDING.featureAccess}
            icon={Lock}
            iconTint="text-emerald-300"
            title="Role-based access, enforced at retrieval."
            body="Every chunk is tagged with which roles can see it. The permission check runs inside the database query itself — restricted content is never retrieved, let alone shown to the model."
          >
            <div className="rounded-lg border border-white/10 bg-black/25 p-3">
              <div className="grid grid-cols-4 gap-2 text-[10px] font-mono uppercase tracking-widest">
                <StageDot label="Query" />
                <StageDot label="Role filter" active />
                <StageDot label="Vector search" />
                <StageDot label="LLM" />
              </div>
              <div className="mt-3 text-xs text-slate-400">The role filter is a WHERE clause in SQL, not an after-the-fact check.</div>
            </div>
          </FeatureCard>

          <FeatureCard
            testId={LANDING.featureAdmin}
            icon={Database}
            iconTint="text-cyan-300"
            title="Admin-managed knowledge base."
            body="Admins upload documents and assign visibility by role — employee, manager, HR, or admin-only — right at upload time. Regular users can only ask questions."
          >
            <div className="rounded-lg border border-white/10 bg-black/25 p-3">
              <div className="text-sm text-slate-100 flex items-center gap-2">
                <FileText className="w-4 h-4 text-cyan-300" /> HR-Compensation-Q3.pdf
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {['employee', 'manager', 'hr', 'admin'].map((r) => (
                  <span key={r} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest ${r === 'hr' || r === 'admin' ? 'border-cyan-400/30 bg-cyan-500/10 text-cyan-200' : 'border-white/10 bg-white/[0.02] text-slate-500'}`}>
                    {(r === 'hr' || r === 'admin') && <ChevronRight className="w-2.5 h-2.5" />}
                    {r}
                  </span>
                ))}
              </div>
            </div>
          </FeatureCard>

          <FeatureCard
            testId={LANDING.featureAudit}
            icon={Activity}
            iconTint="text-emerald-300"
            title="Full visibility into every query."
            body="Every question logs what was retrieved and what was blocked — access control isn't just claimed, it's provable per answer, and it stays in your conversation history."
          >
            <div className="rounded-lg border border-white/10 bg-black/25 p-3 space-y-1.5">
              {[
                { role: 'employee', ret: 2, blk: 3 },
                { role: 'hr', ret: 5, blk: 0 },
                { role: 'admin', ret: 5, blk: 0 },
              ].map((row) => (
                <div key={row.role} className="flex items-center justify-between text-[11px] font-mono">
                  <span className="uppercase tracking-widest text-slate-400">{row.role}</span>
                  <span className="flex items-center gap-1.5">
                    <span className="text-emerald-300">+{row.ret}</span>
                    <span className="text-red-300">-{row.blk}</span>
                  </span>
                </div>
              ))}
            </div>
          </FeatureCard>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pb-24">
        <div className="panel p-8 sm:p-10 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 -mr-16 -mt-16 opacity-30 pointer-events-none">
            <div className="radar-ring inset-0" />
            <div className="radar-ring" style={{ inset: '15%' }} />
          </div>
          <div className="relative">
            <h3 className="font-display font-semibold text-2xl sm:text-3xl tracking-tight">Ready to see it work?</h3>
            <p className="text-slate-400 mt-2 max-w-xl">Log in with your assigned role, or create an account to get started.</p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button
                data-testid={LANDING.finalCtaButton}
                onClick={() => navigate('/login')}
                className="bg-cyan-500 text-slate-900 hover:bg-cyan-400 shadow-[0_0_0_1px_rgba(34,211,238,0.35),0_0_28px_rgba(34,211,238,0.18)] font-medium"
              >
                Access console
                <ArrowRight className="w-4 h-4 ml-1" strokeWidth={1.75} />
              </Button>
              <Link
                to="/register"
                data-testid={LANDING.finalCtaRegister}
                className="text-sm text-slate-300 hover:text-cyan-300 transition-colors underline underline-offset-4 decoration-white/20 hover:decoration-cyan-400/60"
              >
                create an account
              </Link>
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/8 py-6">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between text-xs text-slate-500 font-mono">
          <div>SENTRY/RAG · permission-aware retrieval</div>
          <div className="flex items-center gap-1.5">
            <span className="pulse-dot" style={{ width: 6, height: 6 }} />
            <span>system nominal</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({ testId, icon: Icon, iconTint = 'text-cyan-300', title, body, children }) {
  return (
    <div data-testid={testId} className="panel p-5 sm:p-6 flex flex-col gap-4 hover:border-cyan-400/25 transition-colors">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-white/[0.04] border border-white/10 flex items-center justify-center">
          <Icon className={`w-4 h-4 ${iconTint}`} strokeWidth={1.75} />
        </div>
        <h3 className="font-display font-semibold text-lg text-slate-100 leading-tight">{title}</h3>
      </div>
      <p className="text-sm text-slate-400 leading-relaxed">{body}</p>
      <div className="mt-auto">{children}</div>
    </div>
  );
}

function StageDot({ label, active }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className={`w-6 h-6 rounded-full border ${active ? 'border-cyan-400/60 bg-cyan-500/20' : 'border-white/15 bg-white/[0.02]'} flex items-center justify-center`}>
        <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-cyan-300' : 'bg-slate-500'}`} />
      </div>
      <span className={active ? 'text-cyan-300' : 'text-slate-500'}>{label}</span>
    </div>
  );
}
