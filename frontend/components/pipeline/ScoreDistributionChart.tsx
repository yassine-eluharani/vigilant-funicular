interface ScoreDistributionChartProps {
  distribution: Record<string, number>;
  scored: number;
  pending: number;
}

export function ScoreDistributionChart({ distribution, scored, pending }: ScoreDistributionChartProps) {
  const total = scored + pending;
  const pct = total > 0 ? Math.round((scored / total) * 100) : 0;
  const isRunning = pending > 0;

  const counts = Array.from({ length: 10 }, (_, i) => distribution[String(i + 1)] || 0);
  const maxCount = Math.max(1, ...counts);
  const totalScored = counts.reduce((a, b) => a + b, 0);

  const colorFor = (score: number) =>
    score >= 7 ? "bg-emerald-500" : score >= 4 ? "bg-amber-500" : "bg-red-400";

  return (
    <div className="flex flex-col gap-4">
      {/* Progress header */}
      <div className="flex items-center gap-3">
        {isRunning && (
          <div className="w-4 h-4 border-2 border-void-border border-t-void-accent rounded-full animate-spin-slow shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-void-text">
            {isRunning ? "Scoring jobs against your CV…" : "Scoring complete"}
          </p>
          <p className="text-xs text-void-muted mt-0.5">
            {scored} of {total} jobs scored{isRunning ? ` · ${pct}%` : ""}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      {isRunning && (
        <div className="h-1.5 rounded-full bg-void-raised overflow-hidden">
          <div
            className="h-full rounded-full bg-void-accent transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}

      {/* Distribution chart */}
      {totalScored > 0 && (
        <div>
          <div className="flex items-end gap-2 h-40 px-1">
            {counts.map((count, i) => {
              const score = i + 1;
              const barH = count > 0 ? Math.max(6, Math.round((count / maxCount) * 130)) : 0;
              return (
                <div key={score} className="flex-1 flex flex-col items-center gap-1.5 min-w-0">
                  <span className="text-xs font-mono font-medium text-void-text leading-none h-4">
                    {count > 0 ? count : ""}
                  </span>
                  <div
                    className={`w-full rounded-t transition-all ${count > 0 ? colorFor(score) : "bg-void-raised"}`}
                    style={{ height: `${barH}px` }}
                    title={`Score ${score}: ${count} jobs`}
                  />
                  <span className="text-xs font-mono text-void-muted leading-none">{score}</span>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between mt-2 px-1">
            <span className="text-xs text-void-subtle">Low fit</span>
            <span className="text-xs text-void-subtle">High fit</span>
          </div>
        </div>
      )}
    </div>
  );
}
