"use client";

import { useState, useCallback, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { LogStream } from "@/components/pipeline/LogStream";
import { FunnelChart } from "@/components/pipeline/FunnelChart";
import { ScoreDistributionChart } from "@/components/pipeline/ScoreDistributionChart";
import { useSSE } from "@/lib/hooks/useSSE";
import { useStats } from "@/lib/hooks/useStats";
import { runPipeline, sseTaskUrl } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

export default function PipelinePage() {
  const toast = useToast();
  const { stats } = useStats(15_000);
  const { getToken } = useAuth();
  const [sseToken, setSseToken] = useState<string | null>(null);

  useEffect(() => {
    getToken().then(setSseToken);
  }, [getToken]);

  const [taskId, setTaskId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const sseUrl = taskId ? sseTaskUrl(taskId) : null;
  const { lines, status: sseStatus, reset: resetSSE } = useSSE(sseUrl, sseToken);

  const handleRun = useCallback(async () => {
    setRunning(true);
    resetSSE();
    try {
      const result = await runPipeline({ stages: ["score"] });
      if (result.skipped) {
        toast("No unscored jobs — all caught up.");
        setRunning(false);
        return;
      }
      setTaskId(result.task_id);
      toast("Scoring started");
    } catch (e) {
      toast(`Failed to start scoring: ${e}`, false);
      setRunning(false);
    }
  }, [toast, resetSSE]);

  const isDone = sseStatus === "done" || sseStatus === "error";
  if (isDone && running) setRunning(false);

  return (
    <div className="flex h-full">
      {/* Controls sidebar */}
      <aside className="w-64 shrink-0 border-r border-void-border bg-void-surface overflow-y-auto p-4 flex flex-col gap-6">
        <div>
          <p className="text-xs font-medium text-void-muted uppercase tracking-wider mb-3">Score Jobs</p>
          <p className="text-xs text-void-muted leading-relaxed">
            Scores all unscored jobs against your profile using AI. This runs automatically when you visit the jobs page, but you can trigger it manually here.
          </p>
        </div>

        <div className="bg-void-raised border border-void-border rounded-lg p-3 space-y-2 text-xs text-void-muted">
          <p className="font-medium text-void-text">What happens:</p>
          <p>① Rule pre-filter — visa, location, experience</p>
          <p>② Heuristic rank — skills similarity</p>
          <p>③ LLM deep score — top 100 candidates</p>
        </div>

        <button
          onClick={handleRun}
          disabled={running}
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
              Scoring…
            </>
          ) : (
            <>
              <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                <path d="M6.3 2.841A1.5 1.5 0 0 0 4 4.11V15.89a1.5 1.5 0 0 0 2.3 1.269l9.344-5.89a1.5 1.5 0 0 0 0-2.538L6.3 2.84Z" />
              </svg>
              Score Jobs
            </>
          )}
        </button>
      </aside>

      {/* Main: log + funnel */}
      <div className="flex-1 min-w-0 flex flex-col p-6 gap-6">
        <div>
          <h1 className="text-base font-semibold text-void-text mb-1">Pipeline</h1>
          <p className="text-xs text-void-muted">
            {taskId ? `Task ${taskId} · ${sseStatus}` : "Press Score Jobs to run"}
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-6 flex-1 min-h-0">
          <div className="flex-1 min-h-[400px] lg:min-h-0">
            <LogStream lines={lines} status={sseStatus} />
          </div>

          {stats && (
            <div className="w-full lg:w-80 shrink-0 flex flex-col gap-6">
              <div className="bg-void-surface border border-void-border rounded-lg p-4">
                <h3 className="text-xs font-medium text-void-muted uppercase tracking-wider mb-4">
                  Score Distribution
                </h3>
                <ScoreDistributionChart
                  distribution={stats.score_distribution || {}}
                  scored={stats.funnel.scored}
                  pending={stats.funnel.pending_score}
                />
              </div>

              <div className="bg-void-surface border border-void-border rounded-lg p-4">
                <h3 className="text-xs font-medium text-void-muted uppercase tracking-wider mb-4">
                  Pipeline Funnel
                </h3>
                <FunnelChart funnel={stats.funnel} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
