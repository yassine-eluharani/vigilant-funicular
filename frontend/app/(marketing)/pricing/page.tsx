import Link from "next/link";

const TIERS = [
  {
    name: "Discovery",
    tier: "Tier 1",
    price: "Free",
    sub: "No API key required",
    color: "border-void-border",
    badge: "bg-void-raised text-void-muted",
    cta: "Get started",
    ctaClass: "border border-void-border text-void-text hover:border-void-accent/40 hover:bg-void-raised",
    features: [
      "Job discovery across 5+ major boards",
      "70+ Workday employer portals",
      "Location & title filtering",
      "Job enrichment (full descriptions)",
      "SQLite database — all your data local",
      "Live pipeline dashboard",
      "Docker-ready self-hosting",
    ],
    missing: ["AI fit scoring", "Resume tailoring", "Cover letters", "PDF generation", "Auto-apply"],
  },
  {
    name: "AI Scoring",
    tier: "Tier 2",
    price: "Pay per token",
    sub: "LLM API key required",
    color: "border-void-accent/50",
    badge: "bg-void-accent/15 text-void-accent border-void-accent/30",
    highlight: true,
    cta: "Start scoring",
    ctaClass: "bg-void-accent text-white hover:bg-indigo-500",
    features: [
      "Everything in Tier 1",
      "AI fit scoring 1–10 per job",
      "Tailored resume per job (LLM)",
      "Cover letter per job (LLM)",
      "PDF generation (LaTeX/Pandoc)",
      "Validation: 42 banned words, anti-hallucination",
      "Multi-provider: Gemini · OpenAI · Local LLM",
      "Score dashboard with reasoning",
    ],
    missing: ["Auto-apply workers"],
  },
  {
    name: "Auto-Apply",
    tier: "Tier 3",
    price: "Pay per token",
    sub: "LLM + Chrome + Claude CLI",
    color: "border-purple-500/40",
    badge: "bg-purple-500/15 text-purple-400 border-purple-500/30",
    cta: "Full automation",
    ctaClass: "bg-purple-600 text-white hover:bg-purple-500",
    features: [
      "Everything in Tier 2",
      "Browser automation via Playwright",
      "Claude Code CLI fills forms intelligently",
      "Parallel workers (up to 8)",
      "CAPTCHA solving via CapSolver",
      "Headless or visible browser mode",
      "Continuous mode — keeps applying",
      "Per-worker live status & cost tracking",
    ],
    missing: [],
  },
];

const FAQ = [
  {
    q: "Is there a cloud version?",
    a: "ApplyPilot is self-hosted — it runs on your machine or your own server. Your data (resumes, profile, API keys) never leaves your infrastructure.",
  },
  {
    q: "What LLMs are supported?",
    a: "Gemini 2.5 Flash (recommended, cheapest), any OpenAI-compatible model (GPT-4o-mini, etc.), or a local model via llama.cpp or Ollama.",
  },
  {
    q: "How much does the AI actually cost?",
    a: "With Gemini Flash, tailoring 50 resumes costs roughly $0.50–$1. Scoring 200 jobs costs under $0.20. Scoring alone uses tiny input-only prompts.",
  },
  {
    q: "Do I need Claude CLI for auto-apply?",
    a: "Yes — Tier 3 uses Claude Code CLI to intelligently navigate job application forms. You need a Claude API key for that component.",
  },
  {
    q: "Can I run it without Docker?",
    a: "Absolutely. Install the backend with pip, run Next.js with npm run dev. Docker is provided for convenience, not required.",
  },
];

export default function PricingPage() {
  return (
    <div className="py-20 px-6">
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="text-center mb-16">
          <p className="text-xs font-semibold text-void-accent uppercase tracking-widest mb-3">Pricing</p>
          <h1 className="text-4xl sm:text-5xl font-bold text-void-text mb-4">Simple, usage-based pricing</h1>
          <p className="text-void-muted max-w-xl mx-auto">
            Start free with Tier 1. Pay only for LLM tokens when you want AI scoring or tailoring. No subscriptions, no hidden fees.
          </p>
        </div>

        {/* Tier cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-20">
          {TIERS.map((t) => (
            <div
              key={t.name}
              className={`relative flex flex-col bg-void-surface border-2 ${t.color} rounded-2xl p-7 ${t.highlight ? "shadow-[0_0_60px_-10px_rgba(99,102,241,0.3)]" : ""}`}
            >
              {t.highlight && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-void-accent text-white text-xs font-semibold rounded-full">
                  Most popular
                </div>
              )}

              <div className={`self-start px-2.5 py-1 rounded-lg text-xs font-medium border mb-4 ${t.badge}`}>{t.tier}</div>

              <h2 className="text-xl font-bold text-void-text mb-1">{t.name}</h2>
              <div className="mb-1">
                <span className="text-2xl font-bold font-mono text-void-text">{t.price}</span>
              </div>
              <p className="text-xs text-void-muted mb-6">{t.sub}</p>

              <Link
                href="/register"
                className={`w-full py-2.5 rounded-xl text-sm font-medium text-center transition-colors mb-8 ${t.ctaClass}`}
              >
                {t.cta} →
              </Link>

              <div className="flex-1 space-y-2.5">
                {t.features.map((f) => (
                  <div key={f} className="flex items-start gap-2.5 text-sm text-void-text">
                    <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 text-void-success shrink-0 mt-0.5">
                      <path d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207Z" />
                    </svg>
                    {f}
                  </div>
                ))}
                {t.missing.map((f) => (
                  <div key={f} className="flex items-start gap-2.5 text-sm text-void-subtle">
                    <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 shrink-0 mt-0.5">
                      <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734L9.06 8l3.22 3.22a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L8 9.06l-3.22 3.22a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06Z" />
                    </svg>
                    {f}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Token cost estimator */}
        <div className="bg-void-surface border border-void-border rounded-2xl p-8 mb-20">
          <h2 className="text-lg font-semibold text-void-text mb-6">Estimated LLM costs</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-void-muted uppercase tracking-wider border-b border-void-border">
                  <th className="pb-3 pr-6">Action</th>
                  <th className="pb-3 pr-6">Gemini Flash</th>
                  <th className="pb-3 pr-6">GPT-4o-mini</th>
                  <th className="pb-3">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-void-border/40">
                {[
                  ["Score 100 jobs",    "$0.05–0.10",   "$0.15–0.30",  "Input only — short prompt + description"],
                  ["Tailor 50 resumes", "$0.40–0.80",   "$1.50–3.00",  "Input + output — full JSON resume"],
                  ["50 cover letters",  "$0.20–0.40",   "$0.80–1.50",  "Input + output — ~300 words each"],
                  ["Full run (200 jobs, 40 tailored)", "$0.80–1.50", "$3.00–6.00", "End-to-end pipeline"],
                ].map(([action, gemini, openai, note]) => (
                  <tr key={action as string}>
                    <td className="py-3 pr-6 text-void-text font-medium">{action}</td>
                    <td className="py-3 pr-6 text-void-success font-mono">{gemini}</td>
                    <td className="py-3 pr-6 text-void-warning font-mono">{openai}</td>
                    <td className="py-3 text-void-muted">{note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* FAQ */}
        <div className="max-w-2xl mx-auto">
          <h2 className="text-2xl font-bold text-void-text mb-8 text-center">Frequently asked questions</h2>
          <div className="space-y-4">
            {FAQ.map(({ q, a }) => (
              <div key={q} className="bg-void-surface border border-void-border rounded-xl p-5">
                <h3 className="text-sm font-semibold text-void-text mb-2">{q}</h3>
                <p className="text-sm text-void-muted leading-relaxed">{a}</p>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
