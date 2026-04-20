"use client";

import type { Job } from "@/lib/types";
import { ScoreBadge } from "./ScoreBadge";
import { coverUrl, resumeUrl } from "@/lib/api";

interface JobCardProps {
  job: Job;
  onSelect: (job: Job) => void;
  onDismiss: (job: Job) => void;
  onMarkApplied: (job: Job) => void;
  onUpgrade?: () => void;
}

function CompanyAvatar({ name }: { name: string }) {
  const letter = (name || "?")[0].toUpperCase();
  // Deterministic color from name hash
  const colors = [
    "bg-indigo-500/20 text-indigo-300",
    "bg-emerald-500/20 text-emerald-300",
    "bg-teal-500/20 text-teal-300",
    "bg-amber-500/20 text-amber-300",
    "bg-purple-500/20 text-purple-300",
    "bg-pink-500/20 text-pink-300",
  ];
  const idx = name.charCodeAt(0) % colors.length;
  return (
    <div className={`w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold shrink-0 ${colors[idx]}`}>
      {letter}
    </div>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return null;
  const map: Record<string, string> = {
    applied:   "bg-void-success/15 text-void-success border-void-success/30",
    interview: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
    offer:     "bg-amber-500/15 text-amber-300 border-amber-500/30",
    rejected:  "bg-void-danger/15 text-void-danger border-void-danger/30",
    dismissed: "bg-void-muted/10 text-void-muted border-void-muted/20",
  };
  const style = map[status] ?? "bg-void-raised text-void-muted border-void-border";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${style}`}>
      {status}
    </span>
  );
}

export function JobCard({ job, onSelect, onDismiss, onMarkApplied, onUpgrade }: JobCardProps) {
  if (job.locked) {
    return (
      <div
        className="relative bg-void-surface border border-void-border rounded-lg p-4 overflow-hidden cursor-pointer animate-fade-in"
        onClick={onUpgrade}
      >
        {/* Blurred background content */}
        <div className="blur-sm select-none pointer-events-none">
          <div className="flex items-start gap-3 mb-3">
            <div className="w-9 h-9 rounded-lg bg-void-raised border border-void-border" />
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-medium text-void-text truncate leading-5">{job.title}</h3>
              <div className="h-3 w-24 bg-void-raised rounded mt-1" />
            </div>
            <ScoreBadge score={job.fit_score} size="sm" />
          </div>
          <div className="space-y-1.5 mb-3">
            <div className="h-3 w-full bg-void-raised rounded" />
            <div className="h-3 w-4/5 bg-void-raised rounded" />
          </div>
          <div className="h-8 bg-void-raised rounded border border-void-border" />
        </div>

        {/* Lock overlay */}
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-void-bg/60 backdrop-blur-[1px] gap-2">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/15 border border-amber-500/30">
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5 text-amber-400">
              <path d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6A1.5 1.5 0 0 0 3 7.5v5A1.5 1.5 0 0 0 4.5 14h7a1.5 1.5 0 0 0 1.5-1.5v-5A1.5 1.5 0 0 0 11.5 6V4.5A3.5 3.5 0 0 0 8 1Zm2.5 5V4.5a2.5 2.5 0 0 0-5 0V6h5Z" />
            </svg>
            <span className="text-xs font-medium text-amber-300">
              {job.fit_score}/10 match — Pro only
            </span>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); onUpgrade?.(); }}
            className="text-xs text-void-accent hover:underline"
          >
            Upgrade to unlock →
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="
        group bg-void-surface border border-void-border rounded-lg p-4
        hover:border-void-raised hover:bg-void-raised/40
        transition-colors cursor-pointer animate-fade-in
      "
      onClick={() => onSelect(job)}
    >
      {/* Header row */}
      <div className="flex items-start gap-3 mb-3">
        <CompanyAvatar name={job.company || "?"} />
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-medium text-void-text truncate leading-5">{job.title}</h3>
          <p className="text-xs text-void-muted truncate mt-0.5">{job.company}</p>
        </div>
        <ScoreBadge score={job.fit_score} size="sm" />
      </div>

      {/* Meta row */}
      <div className="flex items-center gap-2 flex-wrap mb-3">
        {job.location && (
          <span className="flex items-center gap-1 text-xs text-void-muted">
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
              <path fillRule="evenodd" d="M7.539 14.841a.75.75 0 0 0 .92 0 10.458 10.458 0 0 0 3.933-5.078 10.413 10.413 0 0 0 .436-2.903C12.828 4.016 10.5 1.75 8 1.75S3.172 4.016 3.172 6.86c0 1.005.145 1.974.436 2.903a10.458 10.458 0 0 0 3.931 5.078ZM8 8.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z" clipRule="evenodd"/>
            </svg>
            {job.location}
          </span>
        )}
        {job.site && (
          <span className="px-1.5 py-0.5 rounded bg-void-raised text-void-muted text-xs border border-void-border">
            {job.site}
          </span>
        )}
        {job.apply_status && <StatusBadge status={job.apply_status} />}
      </div>

      {/* Reasoning preview */}
      {job.score_reasoning && (
        <p className="text-xs text-void-muted line-clamp-2 mb-3 leading-relaxed">
          {job.score_reasoning}
        </p>
      )}

      {/* Action row */}
      <div
        className="flex items-center gap-2 border-t border-void-border pt-3"
        onClick={(e) => e.stopPropagation()}
      >
        {job.has_pdf && (
          <a
            href={resumeUrl(job.url_encoded)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-void-raised border border-void-border text-xs text-void-muted hover:text-void-text hover:border-void-accent/40 transition-colors"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <path d="M4 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V6.414A2 2 0 0 0 13.414 5L10 1.586A2 2 0 0 0 8.586 1H4Zm3.5 7a.5.5 0 0 1 .5.5v2.293l.646-.647a.5.5 0 0 1 .708.708l-1.5 1.5a.5.5 0 0 1-.708 0l-1.5-1.5a.5.5 0 0 1 .708-.708l.646.647V8.5a.5.5 0 0 1 .5-.5Z" />
            </svg>
            Resume
          </a>
        )}
        {job.has_cover_pdf && (
          <a
            href={coverUrl(job.url_encoded)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-void-raised border border-void-border text-xs text-void-muted hover:text-void-text hover:border-void-accent/40 transition-colors"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <path d="M4 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V6.414A2 2 0 0 0 13.414 5L10 1.586A2 2 0 0 0 8.586 1H4ZM5 8.5a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5Zm0 2a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5ZM5.5 5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1 0-1Z" />
            </svg>
            Cover
          </a>
        )}
        {job.application_url && (
          <a
            href={job.application_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-void-accent/10 border border-void-accent/30 text-xs text-void-accent hover:bg-void-accent/20 transition-colors ml-auto"
          >
            Apply
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
              <path fillRule="evenodd" d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5Z" clipRule="evenodd"/>
              <path fillRule="evenodd" d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5Z" clipRule="evenodd"/>
            </svg>
          </a>
        )}
        {job.apply_status !== "dismissed" ? (
          <button
            onClick={() => onDismiss(job)}
            className="px-2.5 py-1.5 rounded border border-void-border text-xs text-void-muted hover:text-void-danger hover:border-void-danger/40 transition-colors ml-auto"
          >
            Dismiss
          </button>
        ) : (
          <button
            onClick={() => onMarkApplied(job)}
            className="px-2.5 py-1.5 rounded border border-void-success/40 text-xs text-void-success hover:bg-void-success/10 transition-colors ml-auto"
          >
            Mark Applied
          </button>
        )}
      </div>
    </div>
  );
}
