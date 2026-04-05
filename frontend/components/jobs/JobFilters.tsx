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
  { value: "pending",   label: "Pending" },
  { value: "ready",     label: "Ready to Apply" },
  { value: "applied",   label: "Applied" },
  { value: "dismissed", label: "Dismissed" },
  { value: "untailored", label: "Untailored" },
];

export function JobFilters({ filters, sites, onChange }: JobFiltersProps) {
  const set = useCallback(
    (patch: Partial<Filters>) => onChange({ ...filters, ...patch }),
    [filters, onChange]
  );

  return (
    <div className="flex flex-col gap-5 p-4">
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
        <div className="flex gap-2 items-center">
          <span className="text-xs text-void-muted w-4">1</span>
          <input
            type="range"
            min={1}
            max={10}
            value={filters.minScore}
            onChange={(e) => set({ minScore: Number(e.target.value) })}
            className="flex-1 accent-void-accent"
          />
          <input
            type="range"
            min={1}
            max={10}
            value={filters.maxScore}
            onChange={(e) => set({ maxScore: Number(e.target.value) })}
            className="flex-1 accent-void-accent"
          />
          <span className="text-xs text-void-muted w-4">10</span>
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
