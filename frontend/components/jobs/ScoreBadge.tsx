"use client";

import { useEffect, useState } from "react";

interface ScoreBadgeProps {
  score: number | null;
  size?: "sm" | "md" | "lg" | "xl";
}

/**
 * Maps a score (1-10) to a tailwind text-color class.
 *
 * Scale (DES-005):
 *   1-4  → muted slate
 *   5-6  → amber  (warm)
 *   7    → teal
 *   8    → emerald
 *   9-10 → gold   (uses --void-gold from design foundation)
 */
function scoreColorClass(score: number | null): string {
  if (!score) return "text-void-muted";
  if (score >= 9) return "text-[var(--void-gold)]";
  if (score >= 8) return "text-emerald-400";
  if (score >= 7) return "text-teal-400";
  if (score >= 5) return "text-amber-400";
  return "text-slate-500";
}

const SIZE_PX = {
  sm: 32,
  md: 40,
  lg: 56,
  xl: 80,
} as const;

const STROKE_PX = {
  sm: 2,
  md: 3,
  lg: 4,
  xl: 5,
} as const;

const TEXT_CLASS = {
  sm: "text-xs",
  md: "text-sm",
  lg: "text-lg",
  xl: "text-2xl",
} as const;

export function ScoreBadge({ score, size = "md" }: ScoreBadgeProps) {
  // Animate fill from 0 → score*10% on first paint.
  // Effect schedules the up-tick via setTimeout so the initial render shows 0%
  // and the browser animates the conic-gradient sweep on the next tick.
  const [fill, setFill] = useState(0);
  useEffect(() => {
    if (!score) return;
    const target = score * 10;
    const id = window.setTimeout(() => setFill(target), 50);
    return () => window.clearTimeout(id);
  }, [score]);

  const px = SIZE_PX[size];
  const stroke = STROKE_PX[size];
  const colorClass = scoreColorClass(score);
  const textClass = TEXT_CLASS[size];
  const useDisplayFont = size === "lg" || size === "xl";
  const isTopScore = !!score && score >= 9;

  // The ring is built from two stacked layers:
  //   • outer conic-gradient (animated fill of currentColor)
  //   • inner mask of background color so only the rim shows
  // We use two divs rather than a border so we can animate the sweep cleanly.
  const ringStyle: React.CSSProperties = {
    width: px,
    height: px,
    background: `conic-gradient(currentColor ${fill}%, color-mix(in srgb, currentColor 12%, transparent) 0)`,
    transition: "background 600ms cubic-bezier(0.16, 1, 0.3, 1)",
    ...(isTopScore
      ? {
          // Inner gold glow for the "this is the one" feel.
          boxShadow: "inset 0 0 0 4px var(--void-gold-glow), 0 0 18px -4px var(--void-gold-glow)",
        }
      : {}),
  };

  const innerStyle: React.CSSProperties = {
    width: px - stroke * 2,
    height: px - stroke * 2,
    backgroundColor: "var(--color-void-surface)",
  };

  return (
    <div
      className={`relative rounded-full flex items-center justify-center shrink-0 ${colorClass} ${
        isTopScore ? "animate-pulse-ring" : ""
      }`}
      style={ringStyle}
      aria-label={score ? `Score ${score} out of 10` : "Unscored"}
      role="img"
    >
      <div
        className="rounded-full flex items-center justify-center"
        style={innerStyle}
      >
        <span
          className={`${textClass} font-bold tabular-nums leading-none ${
            useDisplayFont ? "font-display" : "font-mono"
          }`}
        >
          {score ?? "—"}
        </span>
      </div>
    </div>
  );
}
