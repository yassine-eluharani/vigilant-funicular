"use client";

import { useEffect, useRef, useState } from "react";

interface LogStreamProps {
  lines: string[];
  status: "idle" | "connecting" | "streaming" | "done" | "error";
}

function classifyLine(line: string): string {
  const l = line.toLowerCase();
  if (l.includes("error") || l.includes("failed") || l.includes("traceback")) return "log-error";
  if (l.includes("warn") || l.includes("warning")) return "log-warn";
  return "log-info";
}

export function LogStream({ lines, status }: LogStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll when new lines arrive
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [lines, autoScroll]);

  // Detect manual scroll to pause auto-scroll
  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  };

  const statusIndicator = {
    idle:       <span className="text-void-muted">—</span>,
    connecting: <span className="text-void-warning animate-pulse">● Connecting…</span>,
    streaming:  <span className="text-void-success">● Live</span>,
    done:       <span className="text-void-muted">✓ Done</span>,
    error:      <span className="text-void-danger">✗ Error</span>,
  }[status];

  return (
    <div className="flex flex-col h-full rounded-lg border border-void-border overflow-hidden">
      {/* Terminal header */}
      <div className="flex items-center justify-between px-3 py-2 bg-void-raised border-b border-void-border shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-void-danger/60" />
            <div className="w-3 h-3 rounded-full bg-void-warning/60" />
            <div className="w-3 h-3 rounded-full bg-void-success/60" />
          </div>
          <span className="text-xs font-mono text-void-muted ml-2">pipeline.log</span>
        </div>
        <div className="flex items-center gap-3 text-xs font-mono">
          {statusIndicator}
          <button
            onClick={() => setAutoScroll(true)}
            className="text-void-muted hover:text-void-text transition-colors"
          >
            ↓ Scroll
          </button>
        </div>
      </div>

      {/* Log area */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="log-terminal flex-1 overflow-y-auto"
      >
        {lines.length === 0 ? (
          <span className="text-void-muted italic">
            {status === "idle" ? "Run a pipeline stage to see live output here." : "Waiting for output…"}
          </span>
        ) : (
          lines.map((line, i) => (
            <div key={i} className={classifyLine(line)}>
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
