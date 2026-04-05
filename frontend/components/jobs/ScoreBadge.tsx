interface ScoreBadgeProps {
  score: number | null;
  size?: "sm" | "md" | "lg";
}

function scoreColor(score: number | null): string {
  if (!score) return "text-void-muted border-void-muted/40";
  if (score >= 9)  return "text-score-9 border-score-9/60";
  if (score >= 8)  return "text-score-8 border-score-8/60";
  if (score >= 7)  return "text-score-7 border-score-7/60";
  if (score >= 5)  return "text-score-6 border-score-6/60";
  return "text-score-low border-score-low/40";
}

export function ScoreBadge({ score, size = "md" }: ScoreBadgeProps) {
  const sizeClass = size === "sm" ? "w-8 h-8 text-xs" : size === "lg" ? "w-12 h-12 text-base" : "w-10 h-10 text-sm";

  return (
    <div className={`score-ring ${sizeClass} ${scoreColor(score)}`}>
      {score ?? "—"}
    </div>
  );
}
