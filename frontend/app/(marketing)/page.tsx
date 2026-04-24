import Link from "next/link";

const FEATURES = [
  {
    color: "text-void-accent",
    bg: "bg-void-accent/10 border-void-accent/20",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
      </svg>
    ),
    title: "Multi-source Discovery",
    desc: "Scrapes Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs, and 70+ Workday employer portals simultaneously.",
  },
  {
    color: "text-void-success",
    bg: "bg-void-success/10 border-void-success/20",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" />
      </svg>
    ),
    title: "AI Fit Scoring",
    desc: "LLM scores each job 1–10 against your profile. Zero bias — only skills, experience, and role alignment matter.",
  },
  {
    color: "text-void-teal",
    bg: "bg-void-teal/10 border-void-teal/20",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
      </svg>
    ),
    title: "Resume Tailoring",
    desc: "Generates a custom resume for every job. Banned-words validation and fabrication guards keep it 100% honest.",
  },
  {
    color: "text-void-warning",
    bg: "bg-void-warning/10 border-void-warning/20",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
      </svg>
    ),
    title: "Cover Letters",
    desc: "Position-specific cover letters written with your voice. References real projects and metrics from your profile.",
  },
  {
    color: "text-purple-400",
    bg: "bg-purple-500/10 border-purple-500/20",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25ZM6.75 12h.008v.008H6.75V12Zm0 3h.008v.008H6.75V15Zm0 3h.008v.008H6.75V18Z" />
      </svg>
    ),
    title: "Application Tracker",
    desc: "Mark jobs as applied, track interview stages, offers, and rejections — all in one place.",
  },
  {
    color: "text-void-accent",
    bg: "bg-void-accent/10 border-void-accent/20",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
      </svg>
    ),
    title: "Live Dashboard",
    desc: "Real-time SSE feed shows every worker action. Filter jobs by score, track interviews, offers, and rejections.",
  },
];

const STEPS = [
  { n: "01", title: "Set up your profile", desc: "Import your CV or fill in your skills, experience, and job preferences. Takes 2 minutes." },
  { n: "02", title: "Configure searches", desc: "Choose keywords, locations, and job boards. ApplyPilot discovers hundreds of matching jobs overnight." },
  { n: "03", title: "Review your matches", desc: "Jobs are AI-scored 1–10 against your profile. Filter by fit, browse descriptions, and shortlist the ones worth your time." },
  { n: "04", title: "Tailor, apply, and track", desc: "Generate a tailored resume and cover letter for any job in one click. Apply with confidence, then track your status in the dashboard." },
];

export default function LandingPage() {
  return (
    <div className="overflow-x-hidden">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative min-h-[88vh] flex items-center justify-center px-6 py-24">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-void-accent/8 rounded-full blur-[120px]" />
          <div className="absolute top-1/3 left-1/4 w-[300px] h-[300px] bg-void-success/5 rounded-full blur-[100px]" />
          <div className="absolute inset-0 opacity-[0.025]" style={{
            backgroundImage: "linear-gradient(#6366f1 1px, transparent 1px), linear-gradient(90deg, #6366f1 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }} />
        </div>

        <div className="relative max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-void-accent/10 border border-void-accent/25 text-xs text-void-accent font-medium mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-void-accent animate-pulse inline-block" />
            AI-powered · 5 pipeline stages · Multi-user SaaS
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight mb-6 leading-[1.05]">
            <span className="text-void-text">Stop applying blind.</span>
            <br />
            <span className="bg-gradient-to-r from-void-accent via-purple-400 to-void-teal bg-clip-text text-transparent">Apply with precision.</span>
          </h1>

          <p className="text-lg text-void-muted max-w-2xl mx-auto mb-10 leading-relaxed">
            ApplyPilot discovers jobs across every major board, scores each one against your profile with AI,
            and generates a tailored resume and cover letter — so every application you send is your best.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link href="/register" className="px-7 py-3.5 rounded-xl bg-void-accent text-white font-semibold hover:bg-indigo-500 transition-all hover:scale-[1.02] active:scale-[0.98] text-sm">
              Start for free →
            </Link>
            <Link href="#how-it-works" className="px-7 py-3.5 rounded-xl border border-void-border text-void-muted font-medium hover:text-void-text hover:border-void-accent/40 transition-colors text-sm">
              See how it works
            </Link>
          </div>

          <p className="mt-8 text-xs text-void-subtle">No credit card required · Self-hosted · Open source</p>
        </div>
      </section>

      {/* ── Stats strip ──────────────────────────────────────────────────── */}
      <section className="border-y border-void-border/60 bg-void-surface/30 py-10">
        <div className="max-w-5xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
          {[
            { val: "70+",  label: "Job boards & portals" },
            { val: "5",    label: "Pipeline stages" },
            { val: "< 2¢", label: "Per tailored resume" },
            { val: "1–10", label: "AI fit score per job" },
          ].map(({ val, label }) => (
            <div key={label}>
              <p className="text-3xl font-bold font-mono text-void-text mb-1">{val}</p>
              <p className="text-sm text-void-muted">{label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────────────────── */}
      <section id="features" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-xs font-semibold text-void-accent uppercase tracking-widest mb-3">Everything included</p>
            <h2 className="text-3xl sm:text-4xl font-bold text-void-text mb-4">Everything you need to apply smarter</h2>
            <p className="text-void-muted max-w-xl mx-auto">Automated discovery and scoring surface the best matches — you decide which to pursue, then let AI do the writing.</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((f) => (
              <div key={f.title} className="bg-void-surface border border-void-border rounded-2xl p-6 hover:bg-void-raised/50 transition-colors">
                <div className={`w-10 h-10 rounded-xl border flex items-center justify-center mb-4 ${f.bg} ${f.color}`}>
                  {f.icon}
                </div>
                <h3 className="text-sm font-semibold text-void-text mb-2">{f.title}</h3>
                <p className="text-sm text-void-muted leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section id="how-it-works" className="py-24 px-6 bg-void-surface/20 border-y border-void-border/40">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-xs font-semibold text-void-accent uppercase tracking-widest mb-3">Simple by design</p>
            <h2 className="text-3xl sm:text-4xl font-bold text-void-text mb-4">Four steps to your next job</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {STEPS.map((s) => (
              <div key={s.n} className="flex gap-5 p-6 bg-void-surface border border-void-border rounded-2xl">
                <div className="shrink-0 w-10 h-10 rounded-xl bg-void-accent/10 border border-void-accent/25 flex items-center justify-center">
                  <span className="text-xs font-bold font-mono text-void-accent">{s.n}</span>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-void-text mb-1.5">{s.title}</h3>
                  <p className="text-sm text-void-muted leading-relaxed">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Terminal preview ──────────────────────────────────────────────── */}
      <section className="py-24 px-6">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-10">
            <h2 className="text-2xl font-bold text-void-text mb-3">Watch it run</h2>
            <p className="text-sm text-void-muted">Live log stream from a real pipeline run</p>
          </div>
          <div className="bg-void-surface border border-void-border rounded-2xl overflow-hidden shadow-2xl">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-void-border bg-void-raised">
              <div className="w-3 h-3 rounded-full bg-red-500/70" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/70" />
              <div className="w-3 h-3 rounded-full bg-green-500/70" />
              <span className="ml-3 text-xs text-void-muted font-mono">applypilot — pipeline run</span>
            </div>
            <div className="p-5 font-mono text-xs leading-6 space-y-0.5">
              {([
                ["text-void-muted",   "[00:00] Scoring jobs for user — 198 unscored"],
                ["text-void-muted",   "[00:00] Phase 1: rule pre-filter (visa, location, experience gap)"],
                ["text-void-teal",    "[00:01] ✓ Pre-filter: 152 passed · 46 rejected"],
                ["text-void-muted",   "[00:01] Phase 2: heuristic rank (skills similarity)"],
                ["text-void-teal",    "[00:02] ✓ Top 100 candidates selected for LLM scoring"],
                ["text-void-accent",  "[00:07] ✓ Scored 100 jobs — avg fit: 6.8 · top score: 9"],
                ["text-void-accent",  "[00:07]   ★ 9/10  Stripe — Senior Backend Engineer — Remote"],
                ["text-void-accent",  "[00:07]   ★ 8/10  Vercel — Platform Engineer — Remote"],
                ["text-void-accent",  "[00:07]   ★ 8/10  Linear — Software Engineer — Remote"],
                ["text-void-success", "[00:07] Scoring complete. 34 jobs scored ≥ 7 — ready to review."],
              ] as [string, string][]).map(([c, t], i) => (
                <p key={i} className={c}>{t}</p>
              ))}
              <p className="text-void-muted animate-pulse">█</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Pricing teaser ────────────────────────────────────────────────── */}
      <section className="py-24 px-6 bg-void-surface/20 border-y border-void-border/40">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-xs font-semibold text-void-accent uppercase tracking-widest mb-3">Flexible tiers</p>
          <h2 className="text-3xl font-bold text-void-text mb-4">Start free, scale when ready</h2>
          <p className="text-void-muted mb-10 max-w-lg mx-auto">Free plan includes AI scoring and 3 tailored resumes per month. Upgrade to Pro for unlimited tailoring, cover letters, and full dashboard access.</p>
          <Link href="/pricing" className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-void-border text-sm font-medium text-void-text hover:border-void-accent/40 hover:bg-void-raised transition-colors">
            View pricing →
          </Link>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────────────────────── */}
      <section className="py-32 px-6">
        <div className="max-w-2xl mx-auto text-center relative">
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="w-96 h-64 bg-void-accent/10 rounded-full blur-[80px]" />
          </div>
          <div className="relative">
            <h2 className="text-4xl font-bold text-void-text mb-4">Ready to land your next role?</h2>
            <p className="text-void-muted mb-8">Self-host in minutes. Your data stays on your machine.</p>
            <Link href="/register" className="inline-block px-8 py-4 rounded-xl bg-void-accent text-white font-semibold hover:bg-indigo-500 transition-all hover:scale-[1.02] active:scale-[0.98]">
              Get started free →
            </Link>
          </div>
        </div>
      </section>

    </div>
  );
}
