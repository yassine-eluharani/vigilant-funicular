"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import type { Job } from "@/lib/types";
import { ScoreBadge } from "./ScoreBadge";
import { getJob, saveResume, dismissJob, restoreJob, markApplied, markStatus, downloadResume, downloadCover, tailorJob, coverJob, favoriteJob } from "@/lib/api";
import { useTaskProgress } from "@/lib/hooks/useTaskProgress";
import { useToast } from "@/components/ui/Toast";

interface JobDetailDrawerProps {
  encodedUrl: string | null;
  onClose: () => void;
  onJobUpdated: () => void;
}

const TABS = ["description", "resume", "cover"] as const;
type Tab = (typeof TABS)[number];

/**
 * Score → CSS color value. Mirrors ScoreBadge so the avatar's left border
 * inside the score-ring picks up a related accent.
 */
function scoreColor(score: number | null): string {
  if (!score) return "var(--color-void-border)";
  if (score >= 9) return "var(--void-gold)";
  if (score >= 8) return "#10B981";
  if (score >= 7) return "#14B8A6";
  if (score >= 5) return "#F59E0B";
  return "#64748B";
}

function HeaderAvatar({ name, score }: { name: string; score: number | null }) {
  const safe = name?.trim() || "?";
  const words = safe.split(/\s+/).filter(Boolean);
  const monogram =
    words.length >= 2
      ? (words[0][0] + words[1][0]).toUpperCase()
      : safe.slice(0, 2).toUpperCase();

  return (
    <div
      className="
        w-6 h-6 rounded-md bg-void-raised
        flex items-center justify-center shrink-0
        text-void-text border border-void-border
      "
      style={{ borderLeft: `2px solid ${scoreColor(score)}` }}
      aria-hidden
    >
      <span className="font-display text-[10px] leading-none tracking-tight">
        {monogram}
      </span>
    </div>
  );
}

export function JobDetailDrawer({ encodedUrl, onClose, onJobUpdated }: JobDetailDrawerProps) {
  const toast = useToast();
  const { waitForTask } = useTaskProgress();
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("description");
  const [editingResume, setEditingResume] = useState(false);
  const [resumeText, setResumeText] = useState("");
  const [saving, setSaving] = useState(false);
  const [generatingResume, setGeneratingResume] = useState(false);
  const [generatingCover, setGeneratingCover] = useState(false);
  const [favorited, setFavorited] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (job) setFavorited(!!job.favorited);
  }, [job]);

  useEffect(() => {
    if (!encodedUrl) { setJob(null); return; }
    setLoading(true);
    setActiveTab("description");
    getJob(encodedUrl)
      .then(setJob)
      .catch(() => toast("Failed to load job details", false))
      .finally(() => setLoading(false));
  }, [encodedUrl, toast]);

  useEffect(() => {
    if (job?.resume_text) setResumeText(job.resume_text);
  }, [job]);

  // Close more-menu on outside click
  useEffect(() => {
    if (!moreOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [moreOpen]);

  const handleSaveResume = useCallback(async () => {
    if (!job) return;
    setSaving(true);
    try {
      await saveResume(job.url_encoded, resumeText);
      toast("Resume saved");
      setEditingResume(false);
    } catch {
      toast("Failed to save resume", false);
    } finally {
      setSaving(false);
    }
  }, [job, resumeText, toast]);

  const handleFavorite = useCallback(async () => {
    if (!job) return;
    setFavorited((f) => !f);
    try {
      const res = await favoriteJob(job.url_encoded);
      setFavorited(res.favorited);
    } catch {
      setFavorited((f) => !f);
    }
  }, [job]);

  const handleGenerateResume = useCallback(async () => {
    if (!job) return;
    setMoreOpen(false);
    setGeneratingResume(true);
    try {
      const { task_id } = await tailorJob(job.url_encoded);
      await waitForTask(task_id);
      const updated = await getJob(job.url_encoded);
      setJob(updated);
      toast("Tailored resume generated");
    } catch {
      toast("Failed to generate resume", false);
    } finally {
      setGeneratingResume(false);
    }
  }, [job, waitForTask, toast]);

  const handleGenerateCover = useCallback(async () => {
    if (!job) return;
    setMoreOpen(false);
    setGeneratingCover(true);
    try {
      const { task_id } = await coverJob(job.url_encoded);
      await waitForTask(task_id);
      const updated = await getJob(job.url_encoded);
      setJob(updated);
      toast("Cover letter generated");
    } catch {
      toast("Failed to generate cover letter", false);
    } finally {
      setGeneratingCover(false);
    }
  }, [job, waitForTask, toast]);

  const handleDismiss = useCallback(async () => {
    if (!job) return;
    setMoreOpen(false);
    try {
      await dismissJob(job.url_encoded);
      toast("Job dismissed");
      onJobUpdated();
      onClose();
    } catch {
      toast("Failed to dismiss", false);
    }
  }, [job, toast, onJobUpdated, onClose]);

  const handleMarkApplied = useCallback(async () => {
    if (!job) return;
    setMoreOpen(false);
    try {
      await markApplied(job.url_encoded);
      toast("Marked as applied");
      onJobUpdated();
    } catch {
      toast("Failed to update status", false);
    }
  }, [job, toast, onJobUpdated]);

  const handleMarkStatus = useCallback(async (status: string) => {
    if (!job) return;
    try {
      await markStatus(job.url_encoded, status);
      toast(`Status updated to ${status}`);
      onJobUpdated();
    } catch {
      toast("Failed to update status", false);
    }
  }, [job, toast, onJobUpdated]);

  const handleRestore = useCallback(async () => {
    if (!job) return;
    setMoreOpen(false);
    try {
      await restoreJob(job.url_encoded);
      onJobUpdated();
    } catch {
      toast("Failed to restore", false);
    }
  }, [job, onJobUpdated, toast]);

  if (!encodedUrl) return null;

  const tabIndex = TABS.indexOf(activeTab);
  const applyHref = job?.application_url && job.application_url !== job.url
    ? job.application_url
    : job?.url;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="
        fixed right-0 top-0 bottom-0 z-50
        w-full max-w-2xl bg-void-surface border-l border-void-border
        flex flex-col animate-slide-in-right overflow-hidden
      ">
        {/* Header — large ScoreBadge with overlapping company avatar */}
        <div className="flex items-start gap-4 p-5 border-b border-void-border shrink-0">
          {loading ? (
            <div className="flex-1 space-y-2">
              <div className="skeleton h-7 w-3/4" />
              <div className="skeleton h-4 w-1/2" />
            </div>
          ) : job ? (
            <>
              <div className="relative shrink-0">
                <ScoreBadge score={job.fit_score} size="xl" />
                {/* Bottom-right overlapping company avatar */}
                <div className="absolute -bottom-1 -right-1">
                  <HeaderAvatar name={job.company || "?"} score={job.fit_score} />
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="font-display text-2xl leading-tight text-void-text">
                  {job.title}
                </h2>
                <p className="font-mono text-[11px] uppercase tracking-wider text-void-muted mt-1.5 truncate">
                  {job.company}
                  {job.location && (
                    <>
                      <span className="mx-1.5 opacity-60">•</span>
                      <span className="normal-case tracking-normal">{job.location}</span>
                    </>
                  )}
                </p>
                {job.salary && (
                  <p className="text-xs text-void-success mt-1 font-mono">{job.salary}</p>
                )}
              </div>
            </>
          ) : null}
          {job && (
            <button
              onClick={handleFavorite}
              title={favorited ? "Remove from favorites" : "Add to favorites"}
              className={`p-1 shrink-0 transition-colors ${favorited ? "text-amber-400 hover:text-amber-300" : "text-void-border hover:text-amber-400"}`}
            >
              <svg viewBox="0 0 16 16" fill={favorited ? "currentColor" : "none"} stroke="currentColor" strokeWidth={favorited ? 0 : 1.5} className="w-4 h-4">
                <path d="M3.612 15.443c-.386.198-.824-.149-.746-.592l.83-4.73L.173 6.765c-.329-.314-.158-.888.283-.95l4.898-.696L7.538.792c.197-.39.73-.39.927 0l2.184 4.327 4.898.696c.441.062.612.636.282.95l-3.522 3.356.83 4.73c.078.443-.36.79-.746.592L8 13.187l-4.389 2.256z"/>
              </svg>
            </button>
          )}
          <button onClick={onClose} className="text-void-muted hover:text-void-text p-1 shrink-0">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        </div>

        {/* Closed banner */}
        {job?.closed && (
          <div className="flex items-center gap-2 px-5 py-2.5 bg-void-danger/10 border-b border-void-danger/30 text-xs text-void-danger shrink-0">
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 shrink-0">
              <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm.75 4a.75.75 0 0 0-1.5 0v3.5a.75.75 0 0 0 1.5 0V5ZM8 12a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z" />
            </svg>
            <span>
              This posting is no longer accepting applications. Tailoring is disabled to save your usage.
            </span>
          </div>
        )}

        {/* Segmented tab control — pill background + sliding indicator */}
        {job && (
          <div className="px-5 pt-4 pb-3 shrink-0">
            <div
              role="tablist"
              aria-label="Job detail sections"
              className="
                relative inline-flex p-0.5 rounded-full
                bg-void-raised border border-void-border
              "
            >
              {/* Sliding indicator */}
              <span
                aria-hidden
                className="
                  absolute top-0.5 bottom-0.5 rounded-full
                  bg-void-surface border border-void-border
                  shadow-sm transition-transform duration-200
                "
                style={{
                  width: `calc((100% - 4px) / ${TABS.length})`,
                  transform: `translateX(calc(${tabIndex} * 100%))`,
                  left: 2,
                }}
              />
              {TABS.map((tab) => {
                const empty =
                  (tab === "resume" && !job.resume_text) ||
                  (tab === "cover" && !job.cover_letter_text);
                return (
                  <button
                    key={tab}
                    role="tab"
                    aria-selected={activeTab === tab}
                    onClick={() => setActiveTab(tab)}
                    className={`
                      relative z-10 px-4 py-1.5 rounded-full text-xs font-medium
                      transition-colors min-w-[88px] capitalize
                      ${activeTab === tab
                        ? "text-void-text"
                        : "text-void-muted hover:text-void-text"
                      }
                    `}
                  >
                    {tab}
                    {empty && <span className="ml-1 opacity-40">—</span>}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="p-5 space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className={`skeleton h-4 ${i % 3 === 2 ? "w-2/3" : "w-full"}`} />
              ))}
            </div>
          )}

          {!loading && job && activeTab === "description" && (
            <div className="px-5 pb-5">
              {job.score_reasoning && (
                <div className="mb-5 p-3 rounded-lg bg-void-raised border border-void-border">
                  <p className="text-xs font-medium text-void-muted mb-1">Score reasoning</p>
                  <p className="text-sm text-void-text leading-relaxed">{job.score_reasoning}</p>
                </div>
              )}
              {job.full_description ? (
                /* Editorial prose — display serif at base size, generous leading,
                   capped at prose width. The description is the highest-read
                   surface in the drawer; it deserves real typography. */
                <article className="font-display text-base leading-[1.65] text-void-text max-w-prose whitespace-pre-wrap">
                  {job.full_description}
                </article>
              ) : (
                <p className="text-sm text-void-muted italic">No description available.</p>
              )}
            </div>
          )}

          {!loading && job && activeTab === "resume" && (
            <div className="p-5">
              {job.resume_text ? (
                editingResume ? (
                  <textarea
                    value={resumeText}
                    onChange={(e) => setResumeText(e.target.value)}
                    className="
                      w-full h-[60vh] font-mono text-xs bg-void-raised border border-void-border
                      rounded-lg p-3 text-void-text focus:outline-none focus:border-void-accent/60
                      resize-none leading-relaxed
                    "
                  />
                ) : (
                  <pre className="text-xs text-void-muted whitespace-pre-wrap font-mono leading-relaxed">
                    {job.resume_text}
                  </pre>
                )
              ) : (
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <p className="text-sm text-void-muted">No tailored resume yet.</p>
                  <button
                    onClick={handleGenerateResume}
                    disabled={generatingResume || !!job.closed}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-void-accent-hover disabled:opacity-50 transition-colors"
                  >
                    {generatingResume ? (
                      <>
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Generating…
                      </>
                    ) : (
                      "Generate tailored resume"
                    )}
                  </button>
                </div>
              )}
            </div>
          )}

          {!loading && job && activeTab === "cover" && (
            <div className="p-5">
              {job.cover_letter_text ? (
                <pre className="text-sm text-void-text whitespace-pre-wrap leading-relaxed font-display">
                  {job.cover_letter_text}
                </pre>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <p className="text-sm text-void-muted">No cover letter yet.</p>
                  <button
                    onClick={handleGenerateCover}
                    disabled={generatingCover || !!job.closed}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-void-accent-hover disabled:opacity-50 transition-colors"
                  >
                    {generatingCover ? (
                      <>
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Generating…
                      </>
                    ) : (
                      "Generate cover letter"
                    )}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer — split-button: primary Tailor + chevron menu for the rest */}
        {job && (
          <div className="flex items-center gap-2 p-4 border-t border-void-border shrink-0">
            {/* Resume-tab inline edit/save (kept inline because it's a tab-local
                action — moving it into the more-menu would hide an in-context
                control). */}
            {activeTab === "resume" && job.resume_text && (
              editingResume ? (
                <>
                  <button
                    onClick={handleSaveResume}
                    disabled={saving}
                    className="px-3 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-void-accent-hover disabled:opacity-50 transition-colors"
                  >
                    {saving ? "Saving…" : "Save"}
                  </button>
                  <button
                    onClick={() => { setEditingResume(false); setResumeText(job.resume_text!); }}
                    className="px-3 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text transition-colors"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  onClick={() => setEditingResume(true)}
                  className="px-3 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text transition-colors"
                >
                  Edit
                </button>
              )
            )}

            {/* Right-aligned split button group */}
            <div className="ml-auto flex items-center">
              {/* Primary action — Tailor */}
              <button
                onClick={handleGenerateResume}
                disabled={generatingResume || !!job.closed}
                className="
                  flex items-center gap-2 px-4 py-2
                  rounded-l-lg border border-void-accent/40 bg-void-accent/15
                  text-sm font-medium text-void-accent
                  hover:bg-void-accent/25 disabled:opacity-50 transition-colors
                "
              >
                {generatingResume ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                    Tailoring…
                  </>
                ) : (
                  <>
                    <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                      <path d="M11.013 1.427a1.75 1.75 0 0 1 2.474 0l1.086 1.086a1.75 1.75 0 0 1 0 2.474l-8.61 8.61c-.21.21-.47.364-.756.445l-3.251.93a.75.75 0 0 1-.927-.928l.929-3.25c.081-.286.235-.547.445-.758l8.61-8.61Zm.176 4.823L9.75 4.81l-6.286 6.287a.253.253 0 0 0-.064.108l-.558 1.953 1.953-.558a.253.253 0 0 0 .108-.064Zm1.238-3.763a.25.25 0 0 0-.354 0L10.811 3.75l1.439 1.44 1.263-1.263a.25.25 0 0 0 0-.354Z" />
                    </svg>
                    {job.resume_text ? "Regenerate" : "Tailor"}
                  </>
                )}
              </button>

              {/* Chevron — opens the rest of the actions */}
              <div className="relative" ref={moreRef}>
                <button
                  onClick={() => setMoreOpen((m) => !m)}
                  aria-haspopup="menu"
                  aria-expanded={moreOpen}
                  title="More actions"
                  className="
                    px-2 py-2 rounded-r-lg border border-l-0 border-void-accent/40
                    bg-void-accent/15 text-void-accent
                    hover:bg-void-accent/25 transition-colors
                  "
                >
                  <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                    <path d="M3.22 6.22a.75.75 0 0 1 1.06 0L8 9.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L3.22 7.28a.75.75 0 0 1 0-1.06Z" />
                  </svg>
                </button>

                {moreOpen && (
                  <div
                    role="menu"
                    className="
                      absolute right-0 bottom-full mb-2 z-20
                      min-w-[220px] rounded-lg border border-void-border bg-void-surface
                      shadow-lg shadow-black/40 py-1
                      animate-fade-up
                    "
                  >
                    {applyHref && (
                      <a
                        role="menuitem"
                        href={applyHref}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={() => setMoreOpen(false)}
                        className="block px-3 py-1.5 text-sm text-void-text hover:bg-void-raised"
                      >
                        Apply on site ↗
                      </a>
                    )}

                    <button
                      role="menuitem"
                      onClick={handleGenerateCover}
                      disabled={generatingCover || !!job.closed}
                      className="w-full text-left px-3 py-1.5 text-sm text-void-text hover:bg-void-raised disabled:opacity-50"
                    >
                      {job.cover_letter_text ? "Regenerate cover letter" : "Generate cover letter"}
                    </button>

                    {job.has_pdf && (
                      <button
                        role="menuitem"
                        onClick={() => { setMoreOpen(false); downloadResume(job.url_encoded, job.title).catch((e) => toast(e instanceof Error ? e.message : "Download failed", false)); }}
                        className="w-full text-left px-3 py-1.5 text-sm text-void-text hover:bg-void-raised"
                      >
                        Download resume PDF
                      </button>
                    )}
                    {job.has_cover_pdf && (
                      <button
                        role="menuitem"
                        onClick={() => { setMoreOpen(false); downloadCover(job.url_encoded, job.title).catch((e) => toast(e instanceof Error ? e.message : "Download failed", false)); }}
                        className="w-full text-left px-3 py-1.5 text-sm text-void-text hover:bg-void-raised"
                      >
                        Download cover PDF
                      </button>
                    )}

                    <div className="my-1 border-t border-void-border" />

                    {job.apply_status !== "applied" && (
                      <button
                        role="menuitem"
                        onClick={handleMarkApplied}
                        className="w-full text-left px-3 py-1.5 text-sm text-void-success hover:bg-void-success/10"
                      >
                        Mark applied
                      </button>
                    )}

                    {job.apply_status === "applied" && (
                      <>
                        {(["interview", "offer", "rejected"] as const).map((s) => (
                          <button
                            key={s}
                            role="menuitem"
                            onClick={() => { setMoreOpen(false); handleMarkStatus(s); }}
                            className="w-full text-left px-3 py-1.5 text-sm text-void-text hover:bg-void-raised capitalize"
                          >
                            Mark {s}
                          </button>
                        ))}
                      </>
                    )}

                    {job.apply_status === "dismissed" ? (
                      <button
                        role="menuitem"
                        onClick={handleRestore}
                        className="w-full text-left px-3 py-1.5 text-sm text-void-success hover:bg-void-success/10"
                      >
                        Restore
                      </button>
                    ) : (
                      <button
                        role="menuitem"
                        onClick={handleDismiss}
                        className="w-full text-left px-3 py-1.5 text-sm text-void-danger hover:bg-void-danger/10"
                      >
                        Dismiss
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
