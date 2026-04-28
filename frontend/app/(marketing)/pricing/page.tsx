"use client";

import Link from "next/link";
import { useState } from "react";

type Tier = "free" | "pro";

const TIER_DATA: Record<Tier, {
  label: string;
  price: string;
  priceSub: string;
  sub: string;
  cta: string;
  ctaHref: string;
  ctaClass: string;
  accentColor: string;
  features: { text: string; included: boolean }[];
}> = {
  free: {
    label: "Free",
    price: "$0",
    priceSub: "/ forever",
    sub: "No credit card required.",
    cta: "Get started",
    ctaHref: "/register",
    ctaClass: "border border-void-border text-void-text hover:border-[var(--void-accent)]/40 hover:bg-void-raised",
    accentColor: "var(--color-void-muted)",
    features: [
      { text: "Job discovery across 5+ major boards", included: true },
      { text: "70+ Workday employer portals", included: true },
      { text: "Location & title filtering", included: true },
      { text: "AI fit scoring 1–10 per job", included: true },
      { text: "3 tailored resumes per month", included: true },
      { text: "1 cover letter per month", included: true },
      { text: "Application tracker", included: true },
      { text: "Live scoring dashboard", included: true },
      { text: "Unlimited tailored resumes", included: false },
      { text: "Unlimited cover letters", included: false },
      { text: "High-score jobs (≥ 8) fully visible", included: false },
      { text: "PDF export for every application", included: false },
    ],
  },
  pro: {
    label: "Pro",
    price: "$19",
    priceSub: "/ month",
    sub: "Unlimited AI-powered tailoring.",
    cta: "Upgrade to Pro",
    ctaHref: "/register",
    ctaClass: "bg-[var(--void-accent)] text-white hover:bg-indigo-500",
    accentColor: "var(--void-accent)",
    features: [
      { text: "Job discovery across 5+ major boards", included: true },
      { text: "70+ Workday employer portals", included: true },
      { text: "Location & title filtering", included: true },
      { text: "AI fit scoring 1–10 per job", included: true },
      { text: "Application tracker", included: true },
      { text: "Live scoring dashboard", included: true },
      { text: "All high-match jobs fully visible", included: true },
      { text: "Unlimited tailored resumes", included: true },
      { text: "Unlimited cover letters", included: true },
      { text: "PDF export for every application", included: true },
      { text: "Multi-provider LLM: Gemini · OpenAI · Local", included: true },
      { text: "Priority support", included: true },
    ],
  },
};

const FAQ = [
  {
    q: "Is there a cloud version?",
    a: "ApplyPilot is self-hosted — it runs on your own server. Your data (resumes, profile, API keys) never leaves your infrastructure.",
  },
  {
    q: "What LLMs are supported?",
    a: "Gemini 2.5 Flash (recommended, cheapest), any OpenAI-compatible model (GPT-4o-mini, etc.), or a local model via llama.cpp or Ollama.",
  },
  {
    q: "How much does the AI actually cost?",
    a: "With Gemini Flash, tailoring 50 resumes costs roughly $0.50–$1. Scoring 200 jobs costs under $0.20. The Pro subscription covers the platform — LLM costs are pay-per-use via your own API key.",
  },
  {
    q: "Can I run it without Docker?",
    a: "Absolutely. Install the backend with pip, run Next.js with npm run dev. Docker is provided for convenience, not required.",
  },
  {
    q: "Does ApplyPilot apply to jobs automatically?",
    a: "No — ApplyPilot prepares your materials (tailored resume, cover letter, PDF) so you can apply with confidence. The submission is always yours to do. You track outcomes in the dashboard.",
  },
];

export default function PricingPage() {
  const [tier, setTier] = useState<Tier>("free");
  const data = TIER_DATA[tier];

  return (
    <div className="py-20 px-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <p className="text-xs font-mono text-[var(--void-accent)] uppercase tracking-widest mb-3">
            Pricing
          </p>
          <h1 className="font-display text-4xl sm:text-5xl text-void-text mb-4 leading-[1.05]">
            Simple, honest pricing.
          </h1>
          <p className="text-void-muted max-w-xl mx-auto">
            Start free and score jobs with AI. Upgrade when you want unlimited
            tailoring and full dashboard access.
          </p>
        </div>

        {/* Tier toggle */}
        <div className="flex justify-center mb-10">
          <div
            role="tablist"
            aria-label="Tier"
            className="inline-flex p-1 rounded-xl bg-void-surface border border-void-border"
          >
            {(["free", "pro"] as Tier[]).map((t) => {
              const active = tier === t;
              return (
                <button
                  key={t}
                  role="tab"
                  aria-selected={active}
                  onClick={() => setTier(t)}
                  className={`px-6 py-2 rounded-lg text-sm font-medium transition-all ${
                    active
                      ? "bg-[var(--void-accent)] text-white shadow-[0_0_24px_-8px_rgba(124,124,245,0.6)]"
                      : "text-void-muted hover:text-void-text"
                  }`}
                >
                  {TIER_DATA[t].label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Single morphing card */}
        <div className="max-w-xl mx-auto mb-20">
          <div
            className="relative bg-void-surface border-2 rounded-2xl p-8 transition-all duration-300"
            style={{
              borderColor:
                tier === "pro"
                  ? "color-mix(in srgb, var(--void-accent) 50%, transparent)"
                  : "var(--color-void-border)",
              boxShadow:
                tier === "pro"
                  ? "0 0 60px -10px rgba(124,124,245,0.3)"
                  : "none",
            }}
          >
            <div className="flex items-baseline gap-1 mb-1">
              <span
                key={data.price}
                className="font-display text-5xl text-void-text transition-all duration-300 animate-fade-up"
              >
                {data.price}
              </span>
              <span className="text-base text-void-muted">{data.priceSub}</span>
            </div>
            <p className="text-sm text-void-muted mb-7">{data.sub}</p>

            <Link
              href={data.ctaHref}
              className={`block w-full py-3 rounded-xl text-sm font-medium text-center transition-colors mb-8 ${data.ctaClass}`}
            >
              {data.cta} →
            </Link>

            <div className="space-y-2.5">
              {data.features.map((f, i) => (
                <div
                  key={`${tier}-${f.text}`}
                  className={`flex items-start gap-2.5 text-sm transition-opacity duration-300 ${
                    f.included ? "text-void-text opacity-100" : "text-void-subtle opacity-70"
                  }`}
                  style={{ transitionDelay: `${i * 15}ms` }}
                >
                  {f.included ? (
                    <svg
                      viewBox="0 0 16 16"
                      fill="currentColor"
                      className="w-4 h-4 text-void-success shrink-0 mt-0.5"
                    >
                      <path d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207Z" />
                    </svg>
                  ) : (
                    <svg
                      viewBox="0 0 16 16"
                      fill="currentColor"
                      className="w-4 h-4 shrink-0 mt-0.5"
                    >
                      <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734L9.06 8l3.22 3.22a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L8 9.06l-3.22 3.22a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06Z" />
                    </svg>
                  )}
                  {f.text}
                </div>
              ))}
            </div>
          </div>

          <p className="text-center text-xs text-void-subtle mt-6 font-mono">
            Toggle between tiers to compare. Same card, different shape.
          </p>
        </div>

        {/* Token cost estimator */}
        <div className="bg-void-surface border border-void-border rounded-2xl p-8 mb-20">
          <h2 className="font-display text-2xl text-void-text mb-2">Estimated LLM costs</h2>
          <p className="text-sm text-void-muted mb-6">
            You bring your own API key — these are approximate costs charged by
            the LLM provider, not by ApplyPilot.
          </p>
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
                  ["Score 100 jobs",                    "$0.05–0.10", "$0.15–0.30", "Input only — short prompt + description"],
                  ["Tailor 50 resumes",                 "$0.40–0.80", "$1.50–3.00", "Input + output — full JSON resume"],
                  ["50 cover letters",                  "$0.20–0.40", "$0.80–1.50", "Input + output — ~300 words each"],
                  ["Full run (200 jobs, 40 tailored)",  "$0.80–1.50", "$3.00–6.00", "End-to-end"],
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
          <h2 className="font-display text-3xl text-void-text mb-8 text-center">
            Frequently asked questions
          </h2>
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
