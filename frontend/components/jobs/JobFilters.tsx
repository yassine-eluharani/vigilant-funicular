"use client";

import { useCallback } from "react";

export interface Filters {
  minScore: number;
  maxScore: number;
  site: string;
  search: string;
  status: string;
}

interface JobFiltersProps {
  filters: Filters;
  sites: string[];
  onChange: (f: Filters) => void;
}

const STATUSES = [
  { value: "scored",     label: "All Scored" },
  { value: "pending",    label: "Pending" },
  { value: "favorites",  label: "Favorites" },
  { value: "ready",      label: "Ready to Apply" },
  { value: "applied",    label: "Applied" },
  { value: "dismissed",  label: "Dismissed" },
  { value: "untailored", label: "Untailored" },
];

// Score → tickmark color. Mirrors ScoreBadge's scale so the slider visually
// previews the colour the user is dialling toward.
function tickColor(n: number): string {
  if (n >= 9) return "var(--void-gold, #f5b942)";
  if (n >= 8) return "#34d399"; // emerald-400
  if (n === 7) return "#2dd4bf"; // teal-400
  if (n >= 5) return "#fbbf24"; // amber-400
  return "#475569"; // slate-600
}

export function JobFilters({ filters, sites, onChange }: JobFiltersProps) {
  const set = useCallback(
    (patch: Partial<Filters>) => onChange({ ...filters, ...patch }),
    [filters, onChange]
  );

  // Compute the % positions of the two thumbs along the 1..10 track. The
  // gradient fill underneath sits between these two stops.
  const minPct = ((filters.minScore - 1) / 9) * 100;
  const maxPct = ((filters.maxScore - 1) / 9) * 100;

  return (
    <div className="flex flex-col gap-5 p-4">
      {/* Component-scoped styles for the dual-range slider. We use a plain
          <style> tag (rather than styled-jsx) so we don't depend on a
          StyleRegistry — class names are unique. globals.css is owned by a
          parallel agent. */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
.ap-score-range-track {
  position: relative;
  height: 4px;
  border-radius: 9999px;
  background: var(--color-void-border, #1e2537);
}
.ap-score-range-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 9999px;
  background: linear-gradient(90deg, #fbbf24 0%, #2dd4bf 45%, #34d399 75%, var(--void-gold, #f5b942) 100%);
}
.ap-score-range-input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  background: transparent;
  appearance: none;
  -webkit-appearance: none;
  pointer-events: none;
  accent-color: var(--void-accent, #6366f1);
}
.ap-score-range-input::-webkit-slider-thumb {
  pointer-events: auto;
  appearance: none;
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 9999px;
  background: #fff;
  border: 2px solid var(--color-void-border, #1e2537);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  cursor: pointer;
  transition: transform 120ms ease;
}
.ap-score-range-input::-webkit-slider-thumb:hover {
  transform: scale(1.15);
}
.ap-score-range-input::-moz-range-thumb {
  pointer-events: auto;
  width: 14px;
  height: 14px;
  border-radius: 9999px;
  background: #fff;
  border: 2px solid var(--color-void-border, #1e2537);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  cursor: pointer;
}
.ap-score-range-input::-webkit-slider-runnable-track {
  background: transparent;
  height: 4px;
}
.ap-score-range-input::-moz-range-track {
  background: transparent;
  height: 4px;
}
`,
        }}
      />

      {/* Search */}
      <div>
        <label className="block text-xs font-medium text-void-muted mb-1.5">Search</label>
        <input
          type="text"
          value={filters.search}
          onChange={(e) => set({ search: e.target.value })}
          placeholder="Title, company, location…"
          className="
            w-full px-3 py-2 rounded-lg bg-void-raised border border-void-border
            text-sm text-void-text placeholder:text-void-muted
            focus:outline-none focus:border-void-accent/60
            transition-colors
          "
        />
      </div>

      {/* Status */}
      <div>
        <label className="block text-xs font-medium text-void-muted mb-1.5">Status</label>
        <div className="flex flex-col gap-1">
          {STATUSES.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => set({ status: value })}
              className={`
                w-full text-left px-3 py-1.5 rounded text-xs transition-colors
                ${filters.status === value
                  ? "bg-void-accent/15 text-void-accent border border-void-accent/30"
                  : "text-void-muted hover:text-void-text hover:bg-void-raised border border-transparent"
                }
              `}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Score range */}
      <div>
        <label className="block text-xs font-medium text-void-muted mb-2">
          Score: {filters.minScore}–{filters.maxScore}
        </label>
        <div className="px-1">
          {/* Custom dual-thumb track: two native inputs absolutely-positioned over
              a styled track + gradient fill. Native inputs preserve a11y/keyboard;
              CSS handles the visual polish. */}
          <div className="ap-score-range-track" role="presentation">
            <span
              className="ap-score-range-fill"
              style={{ left: `${minPct}%`, right: `${100 - maxPct}%` }}
            />
            <input
              type="range"
              min={1}
              max={10}
              value={filters.minScore}
              aria-label="Minimum score"
              onChange={(e) =>
                set({ minScore: Math.min(Number(e.target.value), filters.maxScore) })
              }
              className="ap-score-range-input"
            />
            <input
              type="range"
              min={1}
              max={10}
              value={filters.maxScore}
              aria-label="Maximum score"
              onChange={(e) =>
                set({ maxScore: Math.max(Number(e.target.value), filters.minScore) })
              }
              className="ap-score-range-input"
            />
          </div>

          {/* Tickmarks 1..10 — colored to match the score gradient. */}
          <div className="flex justify-between mt-2 px-0.5">
            {Array.from({ length: 10 }).map((_, i) => {
              const n = i + 1;
              const inRange = n >= filters.minScore && n <= filters.maxScore;
              return (
                <span
                  key={n}
                  className="block w-1 h-1.5 rounded-sm transition-opacity"
                  style={{
                    backgroundColor: tickColor(n),
                    opacity: inRange ? 1 : 0.25,
                  }}
                  aria-hidden
                />
              );
            })}
          </div>
          <div className="flex justify-between mt-1 text-[10px] text-void-subtle font-mono">
            <span>1</span>
            <span>10</span>
          </div>
        </div>
      </div>

      {/* Site filter */}
      {sites.length > 0 && (
        <div>
          <label className="block text-xs font-medium text-void-muted mb-1.5">Site</label>
          <div className="flex flex-col gap-1">
            <button
              onClick={() => set({ site: "" })}
              className={`w-full text-left px-3 py-1.5 rounded text-xs transition-colors ${
                !filters.site
                  ? "bg-void-accent/15 text-void-accent border border-void-accent/30"
                  : "text-void-muted hover:text-void-text hover:bg-void-raised border border-transparent"
              }`}
            >
              All sites
            </button>
            {sites.map((s) => (
              <button
                key={s}
                onClick={() => set({ site: s })}
                className={`w-full text-left px-3 py-1.5 rounded text-xs truncate transition-colors ${
                  filters.site === s
                    ? "bg-void-accent/15 text-void-accent border border-void-accent/30"
                    : "text-void-muted hover:text-void-text hover:bg-void-raised border border-transparent"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
