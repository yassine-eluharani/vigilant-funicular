"use client";

import { useState, useCallback } from "react";
import { StageSelector } from "@/components/pipeline/StageSelector";
import { LogStream } from "@/components/pipeline/LogStream";
import { FunnelChart } from "@/components/pipeline/FunnelChart";
import { useSSE } from "@/lib/hooks/useSSE";
import { useStats } from "@/lib/hooks/useStats";
import { runPipeline } from "@/lib/api";
import { sseTaskUrl } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

export default function PipelinePage() {
  const toast = useToast();
  const { stats } = useStats(5_000);

  // Controls
  const [stages, setStages] = useState<string[]>(["discover", "enrich", "filter", "score"]);
  const [minScore, setMinScore] = useState(7);
  const [workers, setWorkers] = useState(1);
  const [validation, setValidation] = useState("normal");
  const [stream, setStream] = useState(false);

  // Task state
  const [taskId, setTaskId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  // SSE log streaming
  const sseUrl = taskId ? sseTaskUrl(taskId) : null;
  const { lines, status: sseStatus, reset: resetSSE } = useSSE(sseUrl);

  const handleRun = useCallback(async () => {
    if (stages.length === 0) {
      toast("Select at least one stage", false);
      return;
    }
    setRunning(true);
    resetSSE();
    try {
      const { task_id } = await runPipeline({ stages, min_score: minScore, workers, validation, stream });
      setTaskId(task_id);
      toast(`Pipeline started (${stages.join(", ")})`);
    } catch (e) {
      toast(`Failed to start pipeline: ${e}`, false);
      setRunning(false);
    }
  }, [stages, minScore, workers, validation, stream, toast, resetSSE]);

  // Reset running state when SSE completes
  const isDone = sseStatus === "done" || sseStatus === "error";
  if (isDone && running) setRunning(false);

  return (
    <div className="flex h-full">
      {/* Controls sidebar */}
      <aside className="w-64 shrink-0 border-r border-void-border bg-void-surface overflow-y-auto p-4 flex flex-col gap-6">
        <StageSelector selected={stages} onChange={setStages} />

        {/* Options */}
        <div>
          <p className="text-xs font-medium text-void-muted uppercase tracking-wider mb-3">Options</p>
          <div className="flex flex-col gap-3">
            <div>
              <label className="text-xs text-void-muted block mb-1">Min Score</label>
              <input
                type="number"
                min={1} max={10}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text focus:outline-none focus:border-void-accent/60 transition-colors"
              />
            </div>
            <div>
              <label className="text-xs text-void-muted block mb-1">Workers</label>
              <input
                type="number"
                min={1} max={8}
                value={workers}
                onChange={(e) => setWorkers(Number(e.target.value))}
                className="w-full px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text focus:outline-none focus:border-void-accent/60 transition-colors"
              />
            </div>
            <div>
              <label className="text-xs text-void-muted block mb-1">Validation</label>
              <select
                value={validation}
                onChange={(e) => setValidation(e.target.value)}
                className="w-full px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text focus:outline-none focus:border-void-accent/60 transition-colors"
              >
                <option value="strict">Strict</option>
                <option value="normal">Normal</option>
                <option value="lenient">Lenient</option>
              </select>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={stream}
                onChange={(e) => setStream(e.target.checked)}
                className="accent-void-accent"
              />
              <span className="text-xs text-void-muted">Streaming mode</span>
            </label>
          </div>
        </div>

        {/* Run button */}
        <button
          onClick={handleRun}
          disabled={running || stages.length === 0}
          className="
            w-full py-2.5 rounded-lg text-sm font-medium transition-colors
            bg-void-accent text-white hover:bg-indigo-500
            disabled:opacity-40 disabled:cursor-not-allowed
            flex items-center justify-center gap-2
          "
        >
          {running ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin-slow" />
              Running…
            </>
          ) : (
            <>
              <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                <path d="M6.3 2.841A1.5 1.5 0 0 0 4 4.11V15.89a1.5 1.5 0 0 0 2.3 1.269l9.344-5.89a1.5 1.5 0 0 0 0-2.538L6.3 2.84Z" />
              </svg>
              Run Pipeline
            </>
          )}
        </button>
      </aside>

      {/* Main: log + funnel */}
      <div className="flex-1 min-w-0 flex flex-col p-6 gap-6">
        <div>
          <h1 className="text-base font-semibold text-void-text mb-1">Pipeline Control</h1>
          <p className="text-xs text-void-muted">
            {taskId ? `Task ${taskId} · ${sseStatus}` : "Select stages and press Run"}
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-6 flex-1 min-h-0">
          {/* Log terminal */}
          <div className="flex-1 min-h-[400px] lg:min-h-0">
            <LogStream lines={lines} status={sseStatus} />
          </div>

          {/* Funnel chart */}
          {stats && (
            <div className="w-full lg:w-72 shrink-0 bg-void-surface border border-void-border rounded-lg p-4">
              <h3 className="text-xs font-medium text-void-muted uppercase tracking-wider mb-4">
                Pipeline Funnel
              </h3>
              <FunnelChart funnel={stats.funnel} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
