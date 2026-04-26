"use client";

import { useEffect, useMemo } from "react";
import type { Stats, UserInfo } from "@/lib/types";

const HIGH_MATCH_THRESHOLD = 8;

function computeUnlockedCount(scoreDistribution: Record<string, number> | undefined): number {
  if (!scoreDistribution) return 0;
  return Object.entries(scoreDistribution)
    .filter(([score]) => Number(score) >= HIGH_MATCH_THRESHOLD)
    .reduce((sum, [, count]) => sum + count, 0);
}

export function ProWelcomeModal({
  stats,
  userInfo,
  onClose,
  onSeeMatches,
}: {
  stats: Stats | null;
  userInfo: UserInfo | null;
  onClose: () => void;
  onSeeMatches: () => void;
}) {
  const unlockedCount = useMemo(
    () => computeUnlockedCount(stats?.score_distribution),
    [stats?.score_distribution],
  );
  const tailored = stats?.tailored ?? 0;
  const firstName = userInfo?.full_name?.split(" ")[0] ?? "";

  // Lock background scroll while modal is open
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  // ESC closes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-md bg-void-surface border border-amber-500/30 rounded-2xl p-7 shadow-2xl animate-pop-in overflow-hidden">
        {/* Decorative sparkles */}
        <Sparkles />

        {/* Glow background */}
        <div
          aria-hidden
          className="absolute -top-24 left-1/2 -translate-x-1/2 w-72 h-72 rounded-full bg-amber-500/15 blur-3xl pointer-events-none"
        />

        <div className="relative">
          {/* Crown */}
          <div className="mx-auto w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-300 to-amber-500 flex items-center justify-center mb-4 shadow-lg shadow-amber-500/30">
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-7 h-7 text-black">
              <path d="M5 16 3 6l5.5 4L12 4l3.5 6L21 6l-2 10H5Zm0 2h14v2H5v-2Z" />
            </svg>
          </div>

          <h2 className="text-center text-xl font-semibold text-void-text mb-1">
            {firstName ? `You're in, ${firstName}.` : "You're in."}
          </h2>
          <p className="text-center text-sm text-void-muted mb-5">
            Welcome to Pro. Your edge just sharpened.
          </p>

          {/* Hero stat */}
          {unlockedCount > 0 && (
            <div className="mb-5 p-5 rounded-xl bg-gradient-to-br from-amber-500/10 via-amber-500/5 to-transparent border border-amber-500/25 text-center animate-count-up">
              <p className="text-5xl font-mono font-semibold text-amber-300 tracking-tight">
                {unlockedCount}
              </p>
              <p className="text-xs uppercase tracking-wider text-amber-400/80 mt-1">
                high-match job{unlockedCount === 1 ? "" : "s"} just unlocked
              </p>
              <p className="text-xs text-void-muted mt-2">
                These were hidden behind the free plan. Now they're yours.
              </p>
            </div>
          )}

          {/* Before / After list */}
          <div className="space-y-2.5 mb-6">
            <BeforeAfter
              label="Tailored resumes"
              before="3 per month"
              after="Unlimited"
            />
            <BeforeAfter
              label="Cover letters"
              before="1 per month"
              after="Unlimited"
            />
            <BeforeAfter
              label="High-match jobs"
              before="Locked"
              after="Fully visible"
            />
            <BeforeAfter
              label="PDF export"
              before="—"
              after="Enabled"
            />
          </div>

          {/* CTA */}
          <button
            onClick={onSeeMatches}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-amber-400 to-amber-500 text-black text-sm font-semibold hover:from-amber-300 hover:to-amber-400 transition-all shadow-lg shadow-amber-500/20"
          >
            {unlockedCount > 0
              ? `Show me my ${unlockedCount} best match${unlockedCount === 1 ? "" : "es"} →`
              : "Take me to my jobs →"}
          </button>

          {/* Activation nudge */}
          <p className="text-center text-xs text-void-subtle mt-4">
            {tailored === 0
              ? "Pro tip: tailor 3 resumes today to start landing interviews."
              : `You've tailored ${tailored} so far — keep the momentum going.`}
          </p>

          {/* Discreet close */}
          <button
            onClick={onClose}
            className="absolute top-0 right-0 w-7 h-7 rounded-full text-void-subtle hover:text-void-muted transition-colors flex items-center justify-center"
            aria-label="Close"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <path d="M4.293 4.293a1 1 0 0 1 1.414 0L8 6.586l2.293-2.293a1 1 0 1 1 1.414 1.414L9.414 8l2.293 2.293a1 1 0 0 1-1.414 1.414L8 9.414l-2.293 2.293a1 1 0 0 1-1.414-1.414L6.586 8 4.293 5.707a1 1 0 0 1 0-1.414Z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

function BeforeAfter({ label, before, after }: { label: string; before: string; after: string }) {
  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-lg bg-void-raised/50 border border-void-border">
      <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 text-void-success shrink-0">
        <path d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207Z" />
      </svg>
      <span className="text-sm text-void-text flex-1">{label}</span>
      <span className="text-xs text-void-subtle line-through">{before}</span>
      <span className="text-xs font-medium text-amber-300">{after}</span>
    </div>
  );
}

function Sparkles() {
  // Six sparkles at different positions / delays for an ambient celebration effect
  const sparkles = [
    { left: "12%", delay: "0s",   size: 10 },
    { left: "28%", delay: "0.4s", size: 6  },
    { left: "45%", delay: "0.8s", size: 8  },
    { left: "62%", delay: "0.2s", size: 5  },
    { left: "78%", delay: "0.6s", size: 9  },
    { left: "90%", delay: "1.0s", size: 7  },
  ];
  return (
    <div aria-hidden className="absolute inset-x-0 bottom-0 h-32 pointer-events-none overflow-hidden">
      {sparkles.map((s, i) => (
        <svg
          key={i}
          viewBox="0 0 24 24"
          fill="currentColor"
          className="absolute bottom-0 text-amber-300 animate-sparkle"
          style={{ left: s.left, width: s.size, height: s.size, animationDelay: s.delay }}
        >
          <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
        </svg>
      ))}
    </div>
  );
}
