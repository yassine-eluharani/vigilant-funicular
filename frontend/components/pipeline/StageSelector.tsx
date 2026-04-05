"use client";

const STAGES = [
  { id: "discover", label: "Discover", desc: "Scrape job boards & Workday portals" },
  { id: "enrich",   label: "Enrich",   desc: "Fetch full descriptions & apply URLs" },
  { id: "filter",   label: "Filter",   desc: "Pre-scoring location filter" },
  { id: "score",    label: "Score",    desc: "LLM job-fit scoring (1–10)" },
  { id: "tailor",   label: "Tailor",   desc: "ATS-optimized resume generation" },
  { id: "cover",    label: "Cover",    desc: "Cover letter generation" },
  { id: "pdf",      label: "PDF",      desc: "Convert to PDF via Playwright" },
];

interface StageSelectorProps {
  selected: string[];
  onChange: (stages: string[]) => void;
}

export function StageSelector({ selected, onChange }: StageSelectorProps) {
  const toggle = (id: string) => {
    if (selected.includes(id)) {
      onChange(selected.filter((s) => s !== id));
    } else {
      onChange([...selected, id]);
    }
  };

  const selectAll = () => onChange(STAGES.map((s) => s.id));
  const clearAll  = () => onChange([]);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-void-muted uppercase tracking-wider">Stages</p>
        <div className="flex gap-2">
          <button onClick={selectAll} className="text-xs text-void-muted hover:text-void-accent transition-colors">All</button>
          <span className="text-void-border">·</span>
          <button onClick={clearAll} className="text-xs text-void-muted hover:text-void-danger transition-colors">None</button>
        </div>
      </div>
      <div className="flex flex-col gap-1">
        {STAGES.map((stage) => {
          const checked = selected.includes(stage.id);
          return (
            <label
              key={stage.id}
              className={`
                flex items-start gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors
                ${checked ? "bg-void-accent/10 border border-void-accent/30" : "border border-transparent hover:bg-void-raised"}
              `}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(stage.id)}
                className="mt-0.5 accent-void-accent"
              />
              <div>
                <p className={`text-sm font-medium ${checked ? "text-void-text" : "text-void-muted"}`}>
                  {stage.label}
                </p>
                <p className="text-xs text-void-muted mt-0.5">{stage.desc}</p>
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}
