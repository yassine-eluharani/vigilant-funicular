"use client";

import { useState, useEffect, useCallback } from "react";
import { useApplyWorkers } from "@/lib/hooks/useApplyWorkers";
import { getSystemStatus, startApply, stopApply } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import type { SystemStatus, WorkerState } from "@/lib/types";

// ── Worker Card ───────────────────────────────────────────────────────────────

function statusBorder(status: string): string {
  switch (status) {
    case "applying":   return "border-l-void-warning";
    case "applied":    return "border-l-void-success";
    case "failed":
    case "expired":    return "border-l-void-danger";
    case "captcha":    return "border-l-purple-500";
    default:           return "border-l-void-border";
  }
}

function statusDot(status: string): string {
  switch (status) {
    case "applying":  return "bg-void-warning animate-pulse";
    case "applied":   return "bg-void-success";
    case "failed":    return "bg-void-danger";
    case "captcha":   return "bg-purple-500";
    default:          return "bg-void-muted";
  }
}

function WorkerCard({ worker }: { worker: WorkerState }) {
  const elapsed = worker.start_time && worker.status === "applying"
    ? `${Math.round(Date.now() / 1000 - worker.start_time)}s`
    : null;

  return (
    <div className={`bg-void-surface border border-void-border border-l-4 ${statusBorder(worker.status)} rounded-lg p-4`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-void-muted font-medium">W{worker.worker_id}</span>
          <div className={`w-2 h-2 rounded-full ${statusDot(worker.status)}`} />
          <span className="text-xs font-medium text-void-text uppercase">{worker.status}</span>
        </div>
        {elapsed && <span className="text-xs font-mono text-void-muted">{elapsed}</span>}
      </div>

      {worker.job_title && (
        <div className="mb-3">
          <p className="text-sm font-medium text-void-text truncate">{worker.job_title}</p>
          <p className="text-xs text-void-muted truncate">{worker.company}</p>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-lg font-semibold font-mono text-void-success">{worker.jobs_applied}</p>
          <p className="text-xs text-void-muted">Applied</p>
        </div>
        <div>
          <p className="text-lg font-semibold font-mono text-void-danger">{worker.jobs_failed}</p>
          <p className="text-xs text-void-muted">Failed</p>
        </div>
        <div>
          <p className="text-lg font-semibold font-mono text-void-warning">
            {worker.total_cost > 0 ? `$${worker.total_cost.toFixed(3)}` : "—"}
          </p>
          <p className="text-xs text-void-muted">Cost</p>
        </div>
      </div>

      {worker.last_action && (
        <p className="mt-3 text-xs text-void-muted truncate border-t border-void-border pt-2">
          {worker.last_action}
        </p>
      )}
    </div>
  );
}

// ── Tier Guard ────────────────────────────────────────────────────────────────

function TierGuard({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getSystemStatus().then(setStatus).catch(() => setStatus(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8"><div className="skeleton h-24 w-96 mx-auto" /></div>;

  if (!status || status.tier < 3) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-8">
        <div className="w-16 h-16 rounded-2xl bg-void-surface border border-void-border flex items-center justify-center mb-4">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-8 h-8 text-void-muted">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
          </svg>
        </div>
        <h2 className="text-base font-semibold text-void-text mb-2">Tier 3 Required</h2>
        <p className="text-sm text-void-muted mb-4 max-w-sm">
          Auto-apply requires Chrome browser and Claude CLI installed on the server.
        </p>
        <div className="flex gap-4 text-sm">
          <span className={`flex items-center gap-1.5 ${status?.has_chrome ? "text-void-success" : "text-void-danger"}`}>
            {status?.has_chrome ? "✓" : "✗"} Chrome
          </span>
          <span className={`flex items-center gap-1.5 ${status?.has_claude_cli ? "text-void-success" : "text-void-danger"}`}>
            {status?.has_claude_cli ? "✓" : "✗"} Claude CLI
          </span>
        </div>
        <p className="text-xs text-void-muted mt-6">
          Install Claude CLI: <code className="font-mono bg-void-raised px-1.5 py-0.5 rounded">npm install -g @anthropic-ai/claude-code</code>
        </p>
      </div>
    );
  }

  return <>{children}</>;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ApplyPage() {
  const toast = useToast();
  const applyData = useApplyWorkers();

  // Controls
  const [workers, setWorkers] = useState(1);
  const [limit, setLimit] = useState(10);
  const [minScore, setMinScore] = useState(7);
  const [headless, setHeadless] = useState(true);
  const [continuous, setContinuous] = useState(false);

  const running = applyData?.running ?? false;

  const handleStart = useCallback(async () => {
    try {
      await startApply({ workers, limit, min_score: minScore, headless, continuous });
      toast("Apply workers started");
    } catch (e) {
      toast(`Failed to start: ${e}`, false);
    }
  }, [workers, limit, minScore, headless, continuous, toast]);

  const handleStop = useCallback(async () => {
    try {
      await stopApply();
      toast("Workers stopped");
    } catch (e) {
      toast(`Failed to stop: ${e}`, false);
    }
  }, [toast]);

  const totals = applyData?.totals ?? { applied: 0, failed: 0, cost: 0 };
  const events = applyData?.events ?? [];
  const workerStates = applyData?.workers ?? [];

  return (
    <TierGuard>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-void-border shrink-0">
          <div>
            <h1 className="text-base font-semibold text-void-text">Apply Tracker</h1>
            <p className="text-xs text-void-muted mt-0.5">
              {running ? (
                <span className="text-void-warning flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-void-warning animate-pulse inline-block" />
                  Running — {workerStates.length} worker{workerStates.length !== 1 ? "s" : ""}
                </span>
              ) : "Idle"}
            </p>
          </div>

          {/* Metrics */}
          <div className="flex items-center gap-6 text-center">
            <div>
              <p className="text-xl font-semibold font-mono text-void-success">{totals.applied}</p>
              <p className="text-xs text-void-muted">Applied</p>
            </div>
            <div>
              <p className="text-xl font-semibold font-mono text-void-danger">{totals.failed}</p>
              <p className="text-xs text-void-muted">Failed</p>
            </div>
            <div>
              <p className="text-xl font-semibold font-mono text-void-warning">
                ${totals.cost.toFixed(3)}
              </p>
              <p className="text-xs text-void-muted">Cost</p>
            </div>
          </div>
        </div>

        <div className="flex flex-1 min-h-0">
          {/* Controls */}
          <aside className="w-56 shrink-0 border-r border-void-border p-4 flex flex-col gap-4">
            <div className="flex flex-col gap-3">
              {[
                { label: "Workers", value: workers, set: setWorkers, min: 1, max: 8 },
                { label: "Limit",   value: limit,   set: setLimit,   min: 0, max: 100 },
                { label: "Min Score", value: minScore, set: setMinScore, min: 1, max: 10 },
              ].map(({ label, value, set, min, max }) => (
                <div key={label}>
                  <label className="text-xs text-void-muted block mb-1">{label}</label>
                  <input
                    type="number"
                    min={min}
                    max={max}
                    value={value}
                    onChange={(e) => set(Number(e.target.value))}
                    disabled={running}
                    className="w-full px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text focus:outline-none focus:border-void-accent/60 disabled:opacity-50 transition-colors"
                  />
                </div>
              ))}

              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={headless} onChange={e => setHeadless(e.target.checked)} disabled={running} className="accent-void-accent" />
                <span className="text-xs text-void-muted">Headless browser</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={continuous} onChange={e => setContinuous(e.target.checked)} disabled={running} className="accent-void-accent" />
                <span className="text-xs text-void-muted">Continuous mode</span>
              </label>
            </div>

            <div className="flex flex-col gap-2 mt-auto">
              <button
                onClick={handleStart}
                disabled={running}
                className="w-full py-2.5 rounded-lg bg-void-success/15 border border-void-success/40 text-sm font-medium text-void-success hover:bg-void-success/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                ▶ Start
              </button>
              <button
                onClick={handleStop}
                disabled={!running}
                className="w-full py-2.5 rounded-lg bg-void-danger/10 border border-void-danger/30 text-sm font-medium text-void-danger hover:bg-void-danger/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                ■ Stop
              </button>
            </div>
          </aside>

          {/* Worker grid + events */}
          <div className="flex-1 min-w-0 p-6 overflow-y-auto">
            {workerStates.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-void-muted">
                <p className="text-sm">No workers active. Press Start to begin.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                {workerStates.map((w) => (
                  <WorkerCard key={w.worker_id} worker={w} />
                ))}
              </div>
            )}

            {/* Events feed */}
            {events.length > 0 && (
              <div className="border border-void-border rounded-lg overflow-hidden">
                <div className="px-4 py-2.5 bg-void-raised border-b border-void-border">
                  <p className="text-xs font-medium text-void-muted uppercase tracking-wider">Recent Events</p>
                </div>
                <div className="divide-y divide-void-border/40">
                  {[...events].reverse().map((e, i) => (
                    <div key={i} className="px-4 py-2 text-xs font-mono text-void-muted hover:text-void-text transition-colors">
                      {e}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </TierGuard>
  );
}
