"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { Job } from "@/lib/types";
import { ScoreBadge } from "./ScoreBadge";
import { downloadCover, downloadResume, tailorJob, coverJob, favoriteJob } from "@/lib/api";
import { useTaskProgress } from "@/lib/hooks/useTaskProgress";
import { useToast } from "@/components/ui/Toast";

interface JobCardProps {
  job: Job;
  onSelect: (job: Job) => void;
  onDismiss: (job: Job) => void;
  onMarkApplied: (job: Job) => void;
  onRefresh: () => void;
}

/**
 * Score → CSS color value. Mirrors ScoreBadge's logic so the card's
 * left spine + the avatar's left border share one color story with the ring.
 */
function scoreColor(score: number | null): string {
  if (!score) return "var(--color-void-border)";
  if (score >= 9) return "var(--void-gold)";
  if (score >= 8) return "#10B981";   // emerald-400 ish
  if (score >= 7) return "#14B8A6";   // teal-400 ish
  if (score >= 5) return "#F59E0B";   // amber-400 ish
  return "#64748B";                    // slate-500 ish
}

/**
 * DES-018 — Monogram avatar.
 *
 * Cleaner than the GitHub-default first-letter-on-hashed-color chip:
 * extracts up to 2 initials from the company name, renders them in
 * the display serif on a neutral chip with a thin colored left border
 * matching the job's fit score (echoes the card's left spine).
 */
function CompanyAvatar({ name, score }: { name: string; score: number | null }) {
  const safe = name?.trim() || "?";
  const words = safe.split(/\s+/).filter(Boolean);
  const monogram =
    words.length >= 2
      ? (words[0][0] + words[1][0]).toUpperCase()
      : safe.slice(0, 2).toUpperCase();

  return (
    <div
      className="
        w-9 h-9 rounded-md bg-void-raised
        flex items-center justify-center shrink-0
        text-void-text
      "
      style={{ borderLeft: `2px solid ${scoreColor(score)}` }}
      aria-hidden
    >
      <span className="font-display text-sm leading-none tracking-tight">
        {monogram}
      </span>
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
    <span className={`px-2 py-0.5 rounded text-[11px] font-medium border ${style}`}>
      {status}
    </span>
  );
}

function Spinner() {
  return <span className="w-3 h-3 border-2 border-current/30 border-t-current rounded-full animate-spin inline-block" />;
}

export function JobCard({ job, onSelect, onDismiss, onMarkApplied, onRefresh }: JobCardProps) {
  const toast = useToast();
  const { waitForTask } = useTaskProgress();
  const [tailoring, setTailoring] = useState(false);
  const [covering, setCovering] = useState(false);
  const [confirmApplied, setConfirmApplied] = useState(false);
  const [favorited, setFavorited] = useState(!!job.favorited);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { setFavorited(!!job.favorited); }, [job.favorited]);

  // Close overflow menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [menuOpen]);

  const handleTailor = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    setTailoring(true);
    try {
      const { task_id } = await tailorJob(job.url_encoded);
      await waitForTask(task_id);
      onRefresh();
    } catch {
      // surfaced via the toast in the catch chain on actions that need it
    } finally {
      setTailoring(false);
    }
  }, [job.url_encoded, waitForTask, onRefresh]);

  const handleFavorite = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    setFavorited((f) => !f); // optimistic
    try {
      const res = await favoriteJob(job.url_encoded);
      setFavorited(res.favorited);
    } catch {
      setFavorited((f) => !f); // revert on error
    }
  }, [job.url_encoded]);

  const handleCover = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpen(false);
    setCovering(true);
    try {
      const { task_id } = await coverJob(job.url_encoded);
      await waitForTask(task_id);
      onRefresh();
    } catch {
      // surfaced via the toast in the catch chain on actions that need it
    } finally {
      setCovering(false);
    }
  }, [job.url_encoded, waitForTask, onRefresh]);

  // Apply destination — prefer the parsed application_url if it's distinct.
  const applyHref = job.application_url && job.application_url !== job.url
    ? job.application_url
    : job.url;

  const color = scoreColor(job.fit_score);
  const isTopScore = !!job.fit_score && job.fit_score >= 9;

  return (
    <div
      className="
        group relative bg-void-surface border border-void-border rounded-lg
        pl-5 pr-4 py-4
        hover:border-void-raised hover:bg-void-raised/40
        hover:-translate-y-px hover:shadow-lg hover:shadow-black/20
        transition-[transform,colors,box-shadow] duration-150
        cursor-pointer animate-fade-up overflow-hidden
      "
      onClick={() => onSelect(job)}
    >
      {/* DES-004 — colored left spine. Mirrors the ScoreBadge color so the
          card has a single color story. Pulses subtly for score≥9. */}
      <span
        aria-hidden
        className={`absolute left-0 top-0 bottom-0 w-[3px] ${isTopScore ? "animate-pulse-ring" : ""}`}
        style={{ backgroundColor: color }}
      />

      {/* Header row: ScoreBadge + Title block (display serif) + favorite */}
      <div className="flex items-start gap-3 mb-3">
        <ScoreBadge score={job.fit_score} size="md" />
        <div className="flex-1 min-w-0">
          <h3 className="font-display text-xl leading-tight text-void-text truncate">
            {job.title}
          </h3>
          <div className="flex items-center gap-1.5 mt-1 min-w-0">
            <CompanyAvatar name={job.company || "?"} score={job.fit_score} />
            <span className="font-mono text-[11px] uppercase tracking-wider text-void-muted truncate">
              {job.company}
              {job.location && (
                <>
                  <span className="mx-1.5 opacity-60">•</span>
                  <span className="normal-case tracking-normal">{job.location}</span>
                </>
              )}
            </span>
          </div>
        </div>
        <button
          onClick={handleFavorite}
          title={favorited ? "Remove from favorites" : "Add to favorites"}
          className={`p-1 rounded shrink-0 transition-colors ${favorited ? "text-amber-400 hover:text-amber-300" : "text-void-border hover:text-amber-400"}`}
        >
          <svg viewBox="0 0 16 16" fill={favorited ? "currentColor" : "none"} stroke="currentColor" strokeWidth={favorited ? 0 : 1.5} className="w-4 h-4">
            <path d="M3.612 15.443c-.386.198-.824-.149-.746-.592l.83-4.73L.173 6.765c-.329-.314-.158-.888.283-.95l4.898-.696L7.538.792c.197-.39.73-.39.927 0l2.184 4.327 4.898.696c.441.062.612.636.282.95l-3.522 3.356.83 4.73c.078.443-.36.79-.746.592L8 13.187l-4.389 2.256z"/>
          </svg>
        </button>
      </div>

      {/* Meta row — site + apply status (location moved into the company line) */}
      {(job.site || job.apply_status) && (
        <div className="flex items-center gap-2 flex-wrap mb-3">
          {job.site && (
            <span className="px-1.5 py-0.5 rounded bg-void-raised text-void-muted text-[11px] border border-void-border">
              {job.site}
            </span>
          )}
          {job.apply_status && <StatusBadge status={job.apply_status} />}
        </div>
      )}

      {/* Reasoning preview — 2-line clamp with a soft fade gradient at the end */}
      {job.score_reasoning && (
        <div className="relative mb-3">
          <p className="text-xs text-void-muted line-clamp-2 leading-relaxed">
            {job.score_reasoning}
          </p>
          <span
            aria-hidden
            className="pointer-events-none absolute inset-y-0 right-0 w-12"
            style={{
              background:
                "linear-gradient(to right, transparent, var(--color-void-surface) 80%)",
            }}
          />
        </div>
      )}

      {/* Action row — two primary actions + overflow */}
      <div
        className="flex items-center gap-2 border-t border-void-border pt-3"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Primary: Tailor */}
        <button
          onClick={handleTailor}
          disabled={tailoring || covering}
          title={job.resume_text ? "Regenerate tailored resume" : "Generate tailored resume"}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-void-accent/30 bg-void-accent/10 text-xs text-void-accent hover:bg-void-accent/20 hover:border-void-accent/50 disabled:opacity-50 transition-colors"
        >
          {tailoring ? <Spinner /> : (
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <path d="M11.013 1.427a1.75 1.75 0 0 1 2.474 0l1.086 1.086a1.75 1.75 0 0 1 0 2.474l-8.61 8.61c-.21.21-.47.364-.756.445l-3.251.93a.75.75 0 0 1-.927-.928l.929-3.25c.081-.286.235-.547.445-.758l8.61-8.61Zm.176 4.823L9.75 4.81l-6.286 6.287a.253.253 0 0 0-.064.108l-.558 1.953 1.953-.558a.253.253 0 0 0 .108-.064Zm1.238-3.763a.25.25 0 0 0-.354 0L10.811 3.75l1.439 1.44 1.263-1.263a.25.25 0 0 0 0-.354Z" />
            </svg>
          )}
          Tailor
        </button>

        {/* Primary: Apply (links out) */}
        <a
          href={applyHref}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-void-border bg-void-raised text-xs text-void-text hover:border-void-accent/40 hover:text-void-accent transition-colors"
        >
          Apply
          <svg viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
            <path fillRule="evenodd" d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5Z" clipRule="evenodd"/>
            <path fillRule="evenodd" d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5Z" clipRule="evenodd"/>
          </svg>
        </a>

        {/* Inline-applied confirmation slot — kept inline because it's a
            destructive-ish state transition that benefits from being visible
            without an extra menu hop. */}
        {confirmApplied && (
          <>
            <button
              onClick={() => { setConfirmApplied(false); onMarkApplied(job); }}
              className="px-2.5 py-1.5 rounded border border-void-success/50 text-xs text-void-success hover:bg-void-success/10 transition-colors"
            >
              Confirm applied
            </button>
            <button
              onClick={() => setConfirmApplied(false)}
              className="px-2.5 py-1.5 rounded border border-void-border text-xs text-void-muted hover:text-void-text transition-colors"
            >
              Cancel
            </button>
          </>
        )}

        {/* Overflow menu — everything else lives here. */}
        <div className="ml-auto relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((m) => !m)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            title="More actions"
            className="px-2 py-1.5 rounded border border-void-border text-void-muted hover:text-void-text hover:border-void-accent/40 transition-colors"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <path d="M3 8a1.25 1.25 0 1 1 2.5 0A1.25 1.25 0 0 1 3 8Zm3.75 0a1.25 1.25 0 1 1 2.5 0 1.25 1.25 0 0 1-2.5 0Zm3.75 0a1.25 1.25 0 1 1 2.5 0 1.25 1.25 0 0 1-2.5 0Z" />
            </svg>
          </button>

          {menuOpen && (
            <div
              role="menu"
              className="
                absolute right-0 bottom-full mb-1 z-20
                min-w-[180px] rounded-lg border border-void-border bg-void-surface
                shadow-lg shadow-black/40 py-1
                animate-fade-up
              "
            >
              <button
                role="menuitem"
                onClick={handleCover}
                disabled={tailoring || covering}
                className="w-full text-left px-3 py-1.5 text-xs text-void-text hover:bg-void-raised flex items-center gap-2 disabled:opacity-50"
              >
                {covering ? <Spinner /> : <span aria-hidden className="w-3" />}
                {job.cover_letter_text ? "Regenerate cover letter" : "Generate cover letter"}
              </button>

              {job.has_pdf && (
                <button
                  role="menuitem"
                  onClick={() => { setMenuOpen(false); downloadResume(job.url_encoded, job.title).catch((e: unknown) => toast(e instanceof Error ? e.message : "Download failed", false)); }}
                  className="w-full text-left px-3 py-1.5 text-xs text-void-text hover:bg-void-raised"
                >
                  Download resume PDF
                </button>
              )}
              {job.has_cover_pdf && (
                <button
                  role="menuitem"
                  onClick={() => { setMenuOpen(false); downloadCover(job.url_encoded, job.title).catch((e: unknown) => toast(e instanceof Error ? e.message : "Download failed", false)); }}
                  className="w-full text-left px-3 py-1.5 text-xs text-void-text hover:bg-void-raised"
                >
                  Download cover PDF
                </button>
              )}

              <a
                role="menuitem"
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setMenuOpen(false)}
                className="block px-3 py-1.5 text-xs text-void-text hover:bg-void-raised"
              >
                View posting
              </a>

              {job.apply_status !== "applied" && !confirmApplied && (
                <button
                  role="menuitem"
                  onClick={() => { setMenuOpen(false); setConfirmApplied(true); }}
                  className="w-full text-left px-3 py-1.5 text-xs text-void-text hover:bg-void-raised"
                >
                  Mark applied…
                </button>
              )}

              {job.apply_status !== "dismissed" && (
                <button
                  role="menuitem"
                  onClick={() => { setMenuOpen(false); onDismiss(job); }}
                  className="w-full text-left px-3 py-1.5 text-xs text-void-danger hover:bg-void-danger/10"
                >
                  Dismiss
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
