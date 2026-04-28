"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { JobCardMock } from "@/components/marketing/JobCardMock";
import { ScoreBadge } from "@/components/jobs/ScoreBadge";

/* ──────────────────────────────────────────────────────────────────────────
 *  Hero stack data
 * ────────────────────────────────────────────────────────────────────────── */

const HERO_CARDS = [
  {
    company: "Stripe",
    title: "Senior Backend Engineer",
    score: 9,
    meta: ["Remote · US", "$210–260k"] as [string, string],
    reasoning:
      "Distributed systems, payments-grade reliability, Postgres at scale — direct match with your last two roles.",
  },
  {
    company: "Linear",
    title: "Staff DevOps Engineer",
    score: 8,
    meta: ["Remote · EU", "$190–230k"] as [string, string],
    reasoning:
      "Kubernetes plus terraform IaC plus async on-call rotation. Their stack overlaps 80% with yours.",
  },
  {
    company: "Vercel",
    title: "Platform Engineer",
    score: 7,
    meta: ["Remote · Global", "$170–210k"] as [string, string],
    reasoning:
      "Edge runtime, observability tooling, developer experience focus. Some Rust desired but not required.",
  },
] as const;

/* ──────────────────────────────────────────────────────────────────────────
 *  Terminal lines (replayed on view)
 * ────────────────────────────────────────────────────────────────────────── */

const TERMINAL_LINES: { c: string; t: string }[] = [
  { c: "text-void-muted",   t: "[00:00] Scoring jobs for user — 198 unscored" },
  { c: "text-void-muted",   t: "[00:00] Phase 1: rule pre-filter (visa, location, experience gap)" },
  { c: "text-void-teal",    t: "[00:01] ✓ Pre-filter: 152 passed · 46 rejected" },
  { c: "text-void-muted",   t: "[00:01] Phase 2: heuristic rank (skills similarity)" },
  { c: "text-void-teal",    t: "[00:02] ✓ Top 100 candidates selected for LLM scoring" },
  { c: "text-void-accent",  t: "[00:07] ✓ Scored 100 jobs — avg fit: 6.8 · top score: 9" },
  { c: "text-void-accent",  t: "[00:07]   ★ 9/10  Stripe — Senior Backend Engineer — Remote" },
  { c: "text-void-accent",  t: "[00:07]   ★ 8/10  Vercel — Platform Engineer — Remote" },
  { c: "text-void-accent",  t: "[00:07]   ★ 8/10  Linear — Software Engineer — Remote" },
  { c: "text-void-success", t: "[00:07] Scoring complete. 34 jobs scored ≥ 7 — ready to review." },
];

/* ──────────────────────────────────────────────────────────────────────────
 *  Stats — editorial style
 * ────────────────────────────────────────────────────────────────────────── */

const STATS = [
  {
    figure: "1–10",
    headline: "Every job, scored against you.",
    sub: "Only the 7+ end up in front of you. The noise stays in the database.",
  },
  {
    figure: "< 2¢",
    headline: "Per scored job.",
    sub: "Self-host, bring your own LLM key, pay your own bill. No middleman markup.",
  },
  {
    figure: "70+",
    headline: "Boards and portals.",
    sub: "Indeed, LinkedIn, Glassdoor, plus Workday employer sites. One pipeline, one inbox.",
  },
];

/* ──────────────────────────────────────────────────────────────────────────
 *  How it works
 * ────────────────────────────────────────────────────────────────────────── */

const STEPS = [
  { n: "01", title: "Set up your profile",  desc: "Import your CV or fill in your skills, experience, and job preferences. Takes 2 minutes." },
  { n: "02", title: "Configure searches",   desc: "Choose keywords, locations, and job boards. ApplyPilot discovers hundreds of matching jobs overnight." },
  { n: "03", title: "Review your matches",  desc: "Jobs are AI-scored 1–10 against your profile. Filter by fit, browse descriptions, and shortlist." },
  { n: "04", title: "Tailor, apply, track", desc: "Generate a tailored resume and cover letter for any job in one click. Track outcomes in the dashboard." },
];

/* ──────────────────────────────────────────────────────────────────────────
 *  IntersectionObserver hook — fires `onEnter` once when element enters view
 * ────────────────────────────────────────────────────────────────────────── */

function useInView<T extends HTMLElement>(threshold = 0.3) {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setInView(true);
            obs.disconnect();
            return;
          }
        }
      },
      { threshold },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, inView };
}

/* ──────────────────────────────────────────────────────────────────────────
 *  Resume diff — fake before/after with highlights
 * ────────────────────────────────────────────────────────────────────────── */

function ResumeDiff() {
  return (
    <div className="grid grid-cols-2 gap-3 bg-void-surface border border-void-border rounded-2xl p-5">
      <div>
        <p className="text-[10px] font-mono uppercase tracking-wider text-void-subtle mb-2">
          Master resume
        </p>
        <p className="text-xs text-void-muted leading-relaxed font-mono">
          Built and maintained{" "}
          <span className="line-through text-void-subtle">internal tools</span>{" "}
          for a 30-engineer team. Reduced{" "}
          <span className="line-through text-void-subtle">build times</span> by
          40%.
        </p>
      </div>
      <div>
        <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--void-accent)] mb-2">
          Tailored — Stripe
        </p>
        <p className="text-xs text-void-text leading-relaxed font-mono">
          Built and maintained{" "}
          <span className="bg-emerald-500/15 text-emerald-300 rounded px-1">
            payments-adjacent infra
          </span>{" "}
          for a 30-engineer team. Reduced{" "}
          <span className="bg-emerald-500/15 text-emerald-300 rounded px-1">
            CI pipeline latency
          </span>{" "}
          by 40%.
        </p>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
 *  Typewriter — streams characters of a cover letter
 * ────────────────────────────────────────────────────────────────────────── */

const COVER_LETTER = `Dear Stripe team,

Reliability at payments scale is what I've spent five years optimizing for —
designing idempotent retry paths, observability that survives a 3am alert,
and migrations that ship without flinching.

The Senior Backend posting reads like the work I want to keep doing.
I'd love to talk.

— Yassine`;

function Typewriter({ start }: { start: boolean }) {
  const [chars, setChars] = useState(0);

  useEffect(() => {
    if (!start) return;
    let cancelled = false;
    let i = 0;
    const tick = () => {
      if (cancelled) return;
      i += 2;
      setChars(Math.min(i, COVER_LETTER.length));
      if (i < COVER_LETTER.length) window.setTimeout(tick, 18);
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, [start]);

  return (
    <div className="bg-void-surface border border-void-border rounded-2xl p-5 h-full">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <p className="text-[10px] font-mono uppercase tracking-wider text-void-subtle">
          Streaming · cover-letter.txt
        </p>
      </div>
      <pre className="text-xs text-void-text leading-relaxed font-mono whitespace-pre-wrap">
        {COVER_LETTER.slice(0, chars)}
        <span className="text-[var(--void-accent)] animate-pulse">█</span>
      </pre>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
 *  Animated terminal — line-by-line reveal on view, with replay
 * ────────────────────────────────────────────────────────────────────────── */

function AnimatedTerminal() {
  const { ref, inView } = useInView<HTMLDivElement>(0.4);
  const [shown, setShown] = useState(0);
  const [tick, setTick] = useState(0); // bumped to retrigger

  useEffect(() => {
    if (!inView && tick === 0) return;
    let i = 0;
    let cancelled = false;
    // Drive `shown` from a single setInterval — first tick (after 1ms) resets
    // to 1, avoiding a synchronous setState in the effect body.
    const id = window.setInterval(() => {
      if (cancelled) return;
      i += 1;
      setShown(i);
      if (i >= TERMINAL_LINES.length) window.clearInterval(id);
    }, 320);
    // Kick off at zero on the next microtask so replays clear the prior list.
    const reset = window.setTimeout(() => {
      if (!cancelled) setShown(0);
    }, 0);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      window.clearTimeout(reset);
    };
  }, [inView, tick]);

  return (
    <div ref={ref} className="bg-void-surface border border-void-border rounded-2xl overflow-hidden shadow-2xl">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-void-border bg-void-raised">
        <div className="w-3 h-3 rounded-full bg-red-500/70" />
        <div className="w-3 h-3 rounded-full bg-yellow-500/70" />
        <div className="w-3 h-3 rounded-full bg-green-500/70" />
        <span className="ml-3 text-xs text-void-muted font-mono">applypilot — pipeline run</span>
        <button
          onClick={() => setTick((n) => n + 1)}
          className="ml-auto text-[11px] text-void-muted hover:text-[var(--void-accent)] font-mono transition-colors"
          aria-label="Replay animation"
        >
          ▶ Replay
        </button>
      </div>
      <div className="p-5 font-mono text-xs leading-6 space-y-0.5 min-h-[260px]">
        {TERMINAL_LINES.slice(0, shown).map((line, i) => (
          <p key={`${tick}-${i}`} className={`${line.c} animate-fade-up`}>
            {line.t}
          </p>
        ))}
        {shown < TERMINAL_LINES.length && (
          <p className="text-void-muted animate-pulse">█</p>
        )}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
 *  Closing CTA — interactive "paste your dream role"
 * ────────────────────────────────────────────────────────────────────────── */

const FAKE_COMPANIES: { name: string; score: number }[] = [
  { name: "Stripe",  score: 9 },
  { name: "Linear",  score: 8 },
  { name: "Vercel",  score: 7 },
];

function CommitmentCTA() {
  const [role, setRole] = useState("");
  const [debouncedRole, setDebouncedRole] = useState("");

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedRole(role.trim()), 500);
    return () => window.clearTimeout(id);
  }, [role]);

  const showCards = debouncedRole.length > 2;
  const encoded = useMemo(() => encodeURIComponent(debouncedRole), [debouncedRole]);
  const ctaHref = showCards
    ? `/register?intent=${encoded}`
    : "/register";

  return (
    <section className="py-32 px-6">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-10">
          <h2 className="font-display text-4xl lg:text-5xl text-void-text leading-[1.05] tracking-tight">
            What role are you actually after?
          </h2>
          <p className="mt-4 text-void-muted">
            Type it. We&rsquo;ll show you what scoring looks like.
          </p>
        </div>

        <div className="relative">
          <input
            type="text"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            placeholder="Senior Backend Engineer"
            className="w-full px-6 py-5 bg-void-surface border border-void-border rounded-2xl text-lg text-void-text placeholder:text-void-subtle focus:outline-none focus:border-[var(--void-accent)] focus:ring-4 focus:ring-[var(--void-accent)]/10 transition-all font-display"
          />
        </div>

        {showCards && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8 stagger-100">
            {FAKE_COMPANIES.map((c, i) => (
              <div
                key={c.name}
                className="animate-fade-up"
                style={{ ["--i" as string]: i } as React.CSSProperties}
              >
                <JobCardMock
                  company={c.name}
                  title={debouncedRole}
                  score={c.score}
                  className="!w-full"
                  meta={["Remote", "$180–240k"]}
                  reasoning={`${c.name} is hiring for this role and your profile lines up — skills, seniority, and stack overlap.`}
                />
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-center mt-10">
          <Link
            href={ctaHref}
            className="px-8 py-4 rounded-xl bg-[var(--void-accent)] text-white font-semibold hover:bg-indigo-500 transition-all hover:scale-[1.02] active:scale-[0.98] text-sm"
          >
            {showCards
              ? `Get scored matches like these →`
              : `Start free →`}
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
 *  Page
 * ────────────────────────────────────────────────────────────────────────── */

export default function LandingPage() {
  // Trigger typewriter / scroll-in effects for the feature row
  const { ref: featureRef, inView: featureInView } = useInView<HTMLDivElement>(0.25);

  return (
    <div className="overflow-x-hidden">

      {/* ── DES-001 Hero — asymmetric, opinionated ───────────────────────── */}
      <section className="px-6 py-20 lg:py-28">
        <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-16 items-center">

          {/* Left — copy */}
          <div>
            <h1 className="font-display text-5xl lg:text-7xl leading-[1.02] tracking-tight text-void-text">
              Most people apply blind.
              <br />
              <span className="text-[var(--void-accent)]">You&rsquo;re done with that.</span>
            </h1>

            <p className="mt-7 max-w-xl text-lg text-void-muted leading-relaxed">
              ApplyPilot scores every job against your resume, then writes the
              application worth sending.
            </p>

            <div className="mt-9 flex items-center gap-5">
              <Link
                href="/register"
                className="px-7 py-3.5 rounded-xl bg-[var(--void-accent)] text-white font-semibold hover:bg-indigo-500 transition-all hover:scale-[1.02] active:scale-[0.98] text-sm"
              >
                Start free →
              </Link>
              <p className="text-xs font-mono text-void-subtle">
                198 jobs scored last 24h · 34 ≥ 7/10
              </p>
            </div>
          </div>

          {/* Right — stacked job-card mocks */}
          <div className="relative h-[420px] hidden lg:block">
            {/* soft ambient shadow */}
            <div
              className="absolute inset-0 -z-10"
              style={{
                boxShadow: "0 60px 80px -40px rgba(124,124,245,0.2)",
                borderRadius: "9999px",
              }}
            />
            <div className="absolute top-0 left-0 rotate-[-4deg]" style={{ opacity: 1 }}>
              <JobCardMock {...HERO_CARDS[0]} />
            </div>
            <div className="absolute top-[100px] left-[40px] rotate-[-1deg]" style={{ opacity: 0.8 }}>
              <JobCardMock {...HERO_CARDS[1]} />
            </div>
            <div className="absolute top-[200px] left-[80px] rotate-[2deg]" style={{ opacity: 0.5 }}>
              <JobCardMock {...HERO_CARDS[2]} />
            </div>
          </div>

          {/* Mobile fallback — show one card centered */}
          <div className="lg:hidden flex justify-center">
            <JobCardMock {...HERO_CARDS[0]} />
          </div>
        </div>
      </section>

      {/* ── DES-007 Stats — editorial, 3 items ───────────────────────────── */}
      <section className="border-y border-void-border/60 bg-void-surface/30 py-16">
        <div className="max-w-5xl mx-auto px-6 grid grid-cols-1 md:grid-cols-3 gap-12">
          {STATS.map((s) => (
            <div key={s.figure}>
              <p className="font-display text-5xl text-void-text leading-none mb-3">
                {s.figure}
              </p>
              <p className="font-display text-lg text-[var(--void-accent)] mb-2">
                {s.headline}
              </p>
              <p className="text-sm text-void-muted leading-relaxed">{s.sub}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── DES-008 Features — 3 with mini-demos ─────────────────────────── */}
      <section id="features" className="py-24 px-6" ref={featureRef}>
        <div className="max-w-6xl mx-auto">
          <div className="mb-16 max-w-2xl">
            <p className="text-xs font-mono text-[var(--void-accent)] uppercase tracking-widest mb-3">
              The pipeline
            </p>
            <h2 className="font-display text-4xl lg:text-5xl text-void-text leading-[1.05] tracking-tight">
              Three things ApplyPilot actually does.
            </h2>
          </div>

          {/* Feature 1 — AI Scoring */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center mb-24">
            <div>
              <p className="text-xs font-mono text-void-subtle uppercase tracking-widest mb-3">
                01 · Scoring
              </p>
              <h3 className="font-display text-3xl text-void-text mb-4 leading-tight">
                Every job rated 1–10 against your profile.
              </h3>
              <p className="text-void-muted leading-relaxed">
                The LLM compares the job description to your skills, experience,
                and stated preferences. Reasoning is recorded — no black box.
              </p>
            </div>
            <div className="bg-void-surface border border-void-border rounded-2xl p-8 flex items-center justify-center min-h-[260px]">
              <div className="flex flex-col items-center gap-4">
                <ScoreBadge score={featureInView ? 9 : null} size="xl" />
                <p className="font-mono text-xs text-void-subtle">stripe — senior backend</p>
              </div>
            </div>
          </div>

          {/* Feature 2 — Resume Tailoring */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center mb-24">
            <div className="lg:order-2">
              <p className="text-xs font-mono text-void-subtle uppercase tracking-widest mb-3">
                02 · Tailoring
              </p>
              <h3 className="font-display text-3xl text-void-text mb-4 leading-tight">
                Your resume, rewritten for one job.
              </h3>
              <p className="text-void-muted leading-relaxed">
                Same facts. Different framing. Banned-words validation and
                fabrication guards keep every claim 100% honest.
              </p>
            </div>
            <div className="lg:order-1">
              <ResumeDiff />
            </div>
          </div>

          {/* Feature 3 — Cover Letter */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div>
              <p className="text-xs font-mono text-void-subtle uppercase tracking-widest mb-3">
                03 · Cover letter
              </p>
              <h3 className="font-display text-3xl text-void-text mb-4 leading-tight">
                Position-specific. In your voice.
              </h3>
              <p className="text-void-muted leading-relaxed">
                References real projects and metrics from your profile. Streams
                in seconds, not days of staring at a blank page.
              </p>
            </div>
            <div>
              <Typewriter start={featureInView} />
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section id="how-it-works" className="py-24 px-6 bg-void-surface/20 border-y border-void-border/40">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-xs font-mono text-[var(--void-accent)] uppercase tracking-widest mb-3">
              Simple by design
            </p>
            <h2 className="font-display text-4xl text-void-text leading-tight">
              Four steps to your next job.
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {STEPS.map((s) => (
              <div key={s.n} className="flex gap-5 p-6 bg-void-surface border border-void-border rounded-2xl">
                <div className="shrink-0 w-10 h-10 rounded-xl bg-void-accent/10 border border-void-accent/25 flex items-center justify-center">
                  <span className="text-xs font-bold font-mono text-[var(--void-accent)]">{s.n}</span>
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

      {/* ── DES-009 Animated terminal ────────────────────────────────────── */}
      <section className="py-24 px-6">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-10">
            <h2 className="font-display text-3xl text-void-text mb-3">Watch it run.</h2>
            <p className="text-sm text-void-muted">Live log stream from a real pipeline run.</p>
          </div>
          <AnimatedTerminal />
        </div>
      </section>

      {/* ── DES-023 Commitment moment CTA ────────────────────────────────── */}
      <CommitmentCTA />

    </div>
  );
}
