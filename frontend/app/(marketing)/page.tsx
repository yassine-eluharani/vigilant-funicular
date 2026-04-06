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
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.59 14.37a6 6 0 0 1-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 0 0 6.16-12.12A14.98 14.98 0 0 0 9.631 8.41m5.96 5.96a14.926 14.926 0 0 1-5.841 2.58m-.119-8.54a6 6 0 0 0-7.381 5.84h4.8m2.581-5.84a14.927 14.927 0 0 0-2.58 5.84m2.699 2.7c-.103.021-.207.041-.311.06a15.09 15.09 0 0 1-2.448-2.448 14.9 14.9 0 0 1 .06-.312m-2.24 2.39a4.493 4.493 0 0 0-1.757 4.306 4.493 4.493 0 0 0 4.306-1.758M16.5 9a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0Z" />
      </svg>
    ),
    title: "Browser Automation",
    desc: "Claude Code CLI drives Chrome to fill forms, solve CAPTCHAs, and submit. Parallel workers, fully headless.",
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
  { n: "02", title: "Configure searches", desc: "Choose keywords, locations, and job boards. ApplyPilot discovers hundreds of matching jobs." },
  { n: "03", title: "Run the pipeline", desc: "Discover → Enrich → Filter → Score → Tailor → Cover → PDF. All automated, all parallel." },
  { n: "04", title: "Auto-apply overnight", desc: "Workers open Chrome, fill applications, and submit — while you sleep." },
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
            AI-powered · 7 pipeline stages · Fully automated
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight mb-6 leading-[1.05]">
            <span className="text-void-text">Apply to </span>
            <span className="bg-gradient-to-r from-void-accent via-purple-400 to-void-teal bg-clip-text text-transparent">100 jobs</span>
            <br />
            <span className="text-void-text">while you sleep</span>
          </h1>

          <p className="text-lg text-void-muted max-w-2xl mx-auto mb-10 leading-relaxed">
            ApplyPilot discovers jobs across every major board, scores them with AI, tailors your resume for each role,
            and submits applications autonomously via browser automation.
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
            { val: "7",    label: "Pipeline stages" },
            { val: "< 2¢", label: "Per tailored resume" },
            { val: "∞",    label: "Applications / night" },
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
            <h2 className="text-3xl sm:text-4xl font-bold text-void-text mb-4">The full pipeline, automated</h2>
            <p className="text-void-muted max-w-xl mx-auto">Every stage from discovery to submission runs in sequence or parallel — no babysitting required.</p>
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
                ["text-void-muted",   "[00:00] Starting pipeline: discover → enrich → filter → score"],
                ["text-void-success", "[00:01] ✓ Discovered 247 jobs (indeed:89 linkedin:94 workday:64)"],
                ["text-void-success", "[00:03] ✓ Enriched 241/247 jobs (6 failed)"],
                ["text-void-teal",    "[00:04] ✓ Location filter: 198 passed, 43 rejected (US-only remote)"],
                ["text-void-accent",  "[00:08] ✓ Scored 198 jobs — avg fit: 6.4 · top score: 9"],
                ["text-void-accent",  "[00:09]   ★ 9/10  Stripe — Senior Backend Engineer — Remote"],
                ["text-void-accent",  "[00:09]   ★ 8/10  Vercel — Platform Engineer — Remote"],
                ["text-void-accent",  "[00:09]   ★ 8/10  Linear — Software Engineer — Remote"],
                ["text-void-warning", "[00:09] Starting tailor stage (workers=4, min_score=7)"],
                ["text-void-success", "[00:41] ✓ Tailored 34 resumes · 34 cover letters · 34 PDFs"],
                ["text-void-success", "[00:41] Pipeline complete. 34 jobs ready to apply."],
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
          <p className="text-void-muted mb-10 max-w-lg mx-auto">Run the full discovery pipeline with no API key. Add an LLM key to unlock AI scoring. Add Chrome + Claude CLI for full auto-apply.</p>
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
