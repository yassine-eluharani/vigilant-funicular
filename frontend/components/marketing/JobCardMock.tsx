"use client";

import { ScoreBadge } from "@/components/jobs/ScoreBadge";

export interface JobCardMockProps {
  company: string;
  title: string;
  score: number;
  /** First letter / monogram for the avatar */
  initial?: string;
  /** Two short meta pills (location, comp, etc.) */
  meta?: [string, string];
  /** A short reasoning snippet shown below */
  reasoning?: string;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Stylized job card for marketing visuals (hero stack, feature demos).
 * NOT the real JobCard — kept intentionally separate to avoid coupling
 * marketing aesthetics to the dashboard component.
 */
export function JobCardMock({
  company,
  title,
  score,
  initial,
  meta = ["Remote", "$180–220k"],
  reasoning = "Strong overlap on backend systems, distributed databases, and on-call experience. Stack matches.",
  className = "",
  style,
}: JobCardMockProps) {
  const ch = (initial ?? company.charAt(0)).toUpperCase();

  return (
    <div
      className={`bg-void-surface border border-void-border rounded-2xl p-5 w-[340px] shadow-2xl ${className}`}
      style={style}
    >
      <div className="flex items-start gap-4">
        {/* Company avatar */}
        <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-void-raised to-void-surface border border-void-border flex items-center justify-center shrink-0">
          <span className="font-display text-lg text-void-text">{ch}</span>
        </div>

        {/* Title + company */}
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-mono uppercase tracking-wider text-void-subtle mb-0.5">
            {company}
          </p>
          <h3 className="text-sm font-semibold text-void-text leading-snug truncate">
            {title}
          </h3>
        </div>

        {/* Score ring */}
        <ScoreBadge score={score} size="md" />
      </div>

      {/* Meta pills */}
      <div className="flex gap-1.5 mt-4">
        {meta.map((m) => (
          <span
            key={m}
            className="px-2 py-0.5 rounded-md bg-void-raised/60 border border-void-border text-[11px] text-void-muted font-mono"
          >
            {m}
          </span>
        ))}
      </div>

      {/* Reasoning preview */}
      <div className="mt-4 pt-3 border-t border-void-border/60">
        <p className="text-[11px] font-mono uppercase tracking-wider text-void-subtle mb-1.5">
          Reasoning
        </p>
        <p className="text-xs text-void-muted leading-relaxed line-clamp-2">
          {reasoning}
        </p>
      </div>
    </div>
  );
}
