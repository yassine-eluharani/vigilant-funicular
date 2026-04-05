import type { Funnel } from "@/lib/types";

interface FunnelChartProps {
  funnel: Funnel;
}

const STAGES: { key: keyof Funnel; label: string; color: string }[] = [
  { key: "discovered",       label: "Discovered",     color: "bg-void-muted/40" },
  { key: "enriched",         label: "Enriched",       color: "bg-indigo-500/40" },
  { key: "scored",           label: "Scored",         color: "bg-purple-500/40" },
  { key: "tailored",         label: "Tailored",       color: "bg-void-accent/60" },
  { key: "cover",            label: "Cover Letter",   color: "bg-teal-500/60" },
  { key: "ready_to_apply",   label: "Ready",          color: "bg-void-warning/60" },
  { key: "applied",          label: "Applied",        color: "bg-void-success/60" },
  { key: "interviews",       label: "Interviews",     color: "bg-emerald-400/80" },
  { key: "offers",           label: "Offers",         color: "bg-emerald-300" },
];

export function FunnelChart({ funnel }: FunnelChartProps) {
  const max = Math.max(funnel.discovered, 1);

  return (
    <div className="flex flex-col gap-2 py-2">
      {STAGES.map(({ key, label, color }) => {
        const value = (funnel[key] as number) || 0;
        const pct = Math.round((value / max) * 100);

        return (
          <div key={key} className="flex items-center gap-3">
            <span className="text-xs text-void-muted w-24 text-right shrink-0">{label}</span>
            <div className="flex-1 h-5 bg-void-raised rounded overflow-hidden border border-void-border relative">
              <div
                className={`h-full ${color} transition-all duration-500 rounded`}
                style={{ width: `${pct}%` }}
              />
              {value > 0 && (
                <span className="absolute inset-0 flex items-center px-2 text-xs font-mono font-medium text-void-text">
                  {value}
                </span>
              )}
            </div>
            <span className="text-xs font-mono text-void-muted w-10 text-right shrink-0">
              {pct}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
