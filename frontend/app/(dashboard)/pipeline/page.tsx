"use client";

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { LogStream } from "@/components/pipeline/LogStream";
import { FunnelChart } from "@/components/pipeline/FunnelChart";
import { useSSE } from "@/lib/hooks/useSSE";
import { useStats } from "@/lib/hooks/useStats";
import { runPipeline, sseTaskUrl } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

// ── Score river ──────────────────────────────────────────────────────────────
//
// We parse the SSE log stream for lines that resemble
//   `<company> · <title>: 8/10` (the scorer prints these). Each parsed score
// becomes a card that streams in from the right. Top scores (≥8) pin to the
// top with a subtle gold glow; sub-7 cards fade out and unmount after 2s.

interface ScoreEvent {
  id: number;
  company: string;
  title: string;
  score: number;
  arrivedAt: number;
}

// Robust parser — accepts a few shapes the scorer might emit. Falls back to
// `null` if the line isn't a score event.
function parseScoreLine(line: string, idCounter: { current: number }): ScoreEvent | null {
  // Common shapes:
  //   "Acme Corp · Senior Engineer: 8/10"
  //   "[score] Acme Corp - Senior Engineer 8/10"
  //   "scored: Acme Corp / Senior Engineer = 8"
  const stripped = line.replace(/^\[[^\]]+]\s*/, "").trim();
  const m = stripped.match(
    /^(?:score(?:d)?:\s*)?(.+?)\s*[·\-/]\s*(.+?)\s*[=:]?\s*(\d{1,2})(?:\s*\/\s*10)?\s*$/i
  );
  if (!m) return null;
  const score = Number(m[3]);
  if (!Number.isFinite(score) || score < 1 || score > 10) return null;
  return {
    id: ++idCounter.current,
    company: m[1].trim(),
    title: m[2].trim(),
    score,
    arrivedAt: Date.now(),
  };
}

function ScoreCard({
  event,
  fading,
}: {
  event: ScoreEvent;
  fading: boolean;
}) {
  const isHigh = event.score >= 8;
  const isElite = event.score >= 9;
  return (
    <div
      className={`
        animate-fade-up rounded-lg border p-3 transition-opacity duration-700
        ${isHigh
          ? "bg-void-surface border-amber-500/30"
          : "bg-void-raised border-void-border"
        }
        ${fading ? "opacity-30" : "opacity-100"}
      `}
      style={isHigh ? { boxShadow: "0 0 24px var(--void-gold-glow)" } : undefined}
    >
      <div className="flex items-center gap-3">
        {/* Score chip */}
        <div
          className={`
            relative shrink-0 flex items-center justify-center w-10 h-10 rounded-lg
            font-mono text-sm font-bold tabular-nums
            ${event.score >= 9
              ? "bg-amber-500/15 text-amber-300 border border-amber-500/40"
              : event.score >= 8
              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/40"
              : event.score >= 7
              ? "bg-teal-500/15 text-teal-300 border border-teal-500/40"
              : event.score >= 5
              ? "bg-amber-500/10 text-amber-200/80 border border-amber-500/20"
              : "bg-void-surface text-void-muted border border-void-border"
            }
          `}
        >
          {isElite && (
            <span className="absolute inset-0 rounded-lg animate-pulse-ring pointer-events-none" />
          )}
          {event.score}
        </div>
        <div className="min-w-0 flex-1">
          <p className={`truncate text-sm ${isHigh ? "font-display text-void-text text-base" : "font-medium text-void-text"}`}>
            {event.company}
          </p>
          <p className="truncate text-xs text-void-muted">{event.title}</p>
        </div>
      </div>
    </div>
  );
}

function ScoreHistogram({ bins }: { bins: number[] }) {
  const max = Math.max(1, ...bins);
  return (
    <div className="bg-void-surface border border-void-border rounded-lg p-4">
      <h3 className="text-xs font-medium text-void-muted uppercase tracking-wider mb-4">
        Live distribution
      </h3>
      <div className="flex items-end gap-1.5 h-32">
        {bins.map((count, i) => {
          const score = i + 1;
          const heightPct = (count / max) * 100;
          const color =
            score >= 9
              ? "bg-amber-400"
              : score >= 8
              ? "bg-emerald-400"
              : score >= 7
              ? "bg-teal-400"
              : score >= 5
              ? "bg-amber-300/60"
              : "bg-void-muted/60";
          return (
            <div key={score} className="flex-1 flex flex-col items-center gap-1.5">
              <div className="w-full h-full flex items-end">
                <div
                  className={`w-full rounded-t transition-all duration-300 ${color}`}
                  style={{ height: `${heightPct}%` }}
                  aria-label={`Score ${score}: ${count} jobs`}
                />
              </div>
              <span className="text-[10px] font-mono text-void-subtle">{score}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

type View = "river" | "logs";

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
  const [view, setView] = useState<View>("river");

  const sseUrl = taskId ? sseTaskUrl(taskId) : null;
  const { lines, status: sseStatus, reset: resetSSE } = useSSE(sseUrl, sseToken);

  // Score-event state. We track:
  //  - `events` : current cards displayed in the river
  //  - `fading` : ids whose 2s fade-out has started
  //  - `bins`   : 10-element histogram, indices 0..9 → scores 1..10
  const [events, setEvents] = useState<ScoreEvent[]>([]);
  const [fading, setFading] = useState<Set<number>>(new Set());
  const [bins, setBins] = useState<number[]>(() => Array(10).fill(0));
  const idCounter = useRef(0);
  const lastProcessedLine = useRef(0);

  // Walk new log lines, parse score events, append to river + histogram.
  // We are bridging an external system (the SSE log stream) into local UI
  // state — exactly the case where the React lint rule allows setState in an
  // effect. The processed-line cursor (`lastProcessedLine`) makes this idempotent.
  useEffect(() => {
    if (lines.length <= lastProcessedLine.current) return;
    const newEvents: ScoreEvent[] = [];
    for (let i = lastProcessedLine.current; i < lines.length; i++) {
      const ev = parseScoreLine(lines[i], idCounter);
      if (ev) newEvents.push(ev);
    }
    lastProcessedLine.current = lines.length;
    if (newEvents.length === 0) return;

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEvents((prev) => [...newEvents.reverse(), ...prev]);
    setBins((prev) => {
      const next = [...prev];
      for (const ev of newEvents) next[ev.score - 1] = (next[ev.score - 1] ?? 0) + 1;
      return next;
    });

    // Schedule fade + removal for sub-7 events.
    for (const ev of newEvents) {
      if (ev.score < 7) {
        setTimeout(() => {
          setFading((prev) => {
            const s = new Set(prev);
            s.add(ev.id);
            return s;
          });
        }, 1300);
        setTimeout(() => {
          setEvents((prev) => prev.filter((e) => e.id !== ev.id));
          setFading((prev) => {
            const s = new Set(prev);
            s.delete(ev.id);
            return s;
          });
        }, 2000);
      }
    }
  }, [lines]);

  const handleRun = useCallback(async () => {
    setRunning(true);
    resetSSE();
    setEvents([]);
    setBins(Array(10).fill(0));
    setFading(new Set());
    lastProcessedLine.current = 0;
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
  // Flip `running` off in an effect once SSE reports a terminal state —
  // doing it during render would cause the "Cannot update a component while
  // rendering a different component" warning. The lint rule for setState
  // in effects is intentionally bypassed here: we *are* synchronising local
  // UI state with an external system (the SSE stream's terminal status).
  useEffect(() => {
    if (isDone) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRunning(false);
    }
  }, [isDone]);

  // High-scoring (≥8) cards stay pinned at top, in arrival order. Lower
  // scores fall below them, in reverse-arrival (newest first).
  const sortedEvents = useMemo(() => {
    const high = events.filter((e) => e.score >= 8);
    const low = events.filter((e) => e.score < 8);
    return [...high, ...low];
  }, [events]);

  return (
    <main className="page-accent-pipeline flex h-full">
      {/* Controls sidebar */}
      <aside className="w-64 shrink-0 border-r border-void-border bg-void-surface overflow-y-auto p-4 flex flex-col gap-6">
        <div>
          <h2 className="font-display text-xl text-void-text mb-2">Score Jobs</h2>
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
            bg-void-accent text-white hover:bg-void-accent-hover
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

        {stats && (
          <div className="bg-void-surface border border-void-border rounded-lg p-4">
            <h3 className="text-xs font-medium text-void-muted uppercase tracking-wider mb-4">
              Pipeline Funnel
            </h3>
            <FunnelChart funnel={stats.funnel} />
          </div>
        )}
      </aside>

      {/* Main: river + logs */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Header + view tabs */}
        <div className="flex items-end justify-between px-6 pt-5 pb-0 border-b border-void-border shrink-0">
          <div>
            <h1 className="font-display text-3xl text-void-text leading-tight">
              Pipeline
            </h1>
            <p className="text-xs text-void-muted mt-1">
              {taskId ? `Task ${taskId} · ${sseStatus}` : "Press Score Jobs to run"}
            </p>
          </div>
          <div className="flex gap-1 -mb-px">
            {(["river", "logs"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`
                  px-4 h-10 rounded-t-lg text-sm border-b-2 transition-colors capitalize
                  ${view === v
                    ? "border-void-teal text-void-teal font-display"
                    : "border-transparent text-void-muted hover:text-void-text"
                  }
                `}
              >
                {v === "river" ? "Live river" : "Logs"}
              </button>
            ))}
          </div>
        </div>

        {/* View content */}
        <div className="flex-1 min-h-0 overflow-hidden p-6">
          {view === "river" ? (
            <div className="flex flex-col h-full gap-5">
              {/* Histogram on top */}
              <ScoreHistogram bins={bins} />

              {/* Live cards */}
              <div className="flex-1 min-h-0 overflow-y-auto pr-1">
                {sortedEvents.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center text-void-muted py-10">
                    <p className="font-display text-2xl text-void-text mb-2">
                      Waiting for the first match.
                    </p>
                    <p className="text-sm">
                      {running
                        ? "Scores will fly in here as the LLM ranks each candidate."
                        : "Press Score Jobs and watch them stream."}
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {sortedEvents.map((ev) => (
                      <ScoreCard
                        key={ev.id}
                        event={ev}
                        fading={fading.has(ev.id)}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="h-full">
              <LogStream lines={lines} status={sseStatus} />
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
