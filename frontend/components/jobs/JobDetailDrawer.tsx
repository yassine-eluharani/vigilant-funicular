"use client";

import { useEffect, useState, useCallback } from "react";
import type { Job } from "@/lib/types";
import { ScoreBadge } from "./ScoreBadge";
import { getJob, saveResume, dismissJob, restoreJob, markApplied, markStatus, resumeUrl, coverUrl, tailorJob, coverJob, favoriteJob, getTask } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

interface JobDetailDrawerProps {
  encodedUrl: string | null;
  onClose: () => void;
  onJobUpdated: () => void;
}

export function JobDetailDrawer({ encodedUrl, onClose, onJobUpdated }: JobDetailDrawerProps) {
  const toast = useToast();
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"description" | "resume" | "cover">("description");
  const [editingResume, setEditingResume] = useState(false);
  const [resumeText, setResumeText] = useState("");
  const [saving, setSaving] = useState(false);
  const [generatingResume, setGeneratingResume] = useState(false);
  const [generatingCover, setGeneratingCover] = useState(false);
  const [favorited, setFavorited] = useState(false);

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

  const pollUntilDone = useCallback(async (taskId: string) => {
    while (true) {
      await new Promise((r) => setTimeout(r, 1500));
      const task = await getTask(taskId);
      if (task.status === "done" || task.status === "error") break;
    }
  }, []);

  const handleGenerateResume = useCallback(async () => {
    if (!job) return;
    setGeneratingResume(true);
    try {
      const { task_id } = await tailorJob(job.url_encoded);
      await pollUntilDone(task_id);
      const updated = await getJob(job.url_encoded);
      setJob(updated);
      toast("Tailored resume generated");
    } catch {
      toast("Failed to generate resume", false);
    } finally {
      setGeneratingResume(false);
    }
  }, [job, pollUntilDone, toast]);

  const handleGenerateCover = useCallback(async () => {
    if (!job) return;
    setGeneratingCover(true);
    try {
      const { task_id } = await coverJob(job.url_encoded);
      await pollUntilDone(task_id);
      const updated = await getJob(job.url_encoded);
      setJob(updated);
      toast("Cover letter generated");
    } catch {
      toast("Failed to generate cover letter", false);
    } finally {
      setGeneratingCover(false);
    }
  }, [job, pollUntilDone, toast]);

  const handleDismiss = useCallback(async () => {
    if (!job) return;
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

  if (!encodedUrl) return null;

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
        {/* Header */}
        <div className="flex items-start gap-4 p-5 border-b border-void-border shrink-0">
          {loading ? (
            <div className="flex-1 space-y-2">
              <div className="skeleton h-5 w-3/4" />
              <div className="skeleton h-4 w-1/2" />
            </div>
          ) : job ? (
            <>
              <ScoreBadge score={job.fit_score} size="lg" />
              <div className="flex-1 min-w-0">
                <h2 className="text-base font-semibold text-void-text leading-snug">{job.title}</h2>
                <p className="text-sm text-void-muted mt-0.5">{job.company} · {job.location}</p>
                {job.salary && <p className="text-xs text-void-success mt-1 font-mono">{job.salary}</p>}
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

        {/* Tabs */}
        {job && (
          <div className="flex border-b border-void-border shrink-0 px-5">
            {(["description", "resume", "cover"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`
                  py-3 px-4 text-sm font-medium border-b-2 -mb-px transition-colors
                  ${activeTab === tab
                    ? "border-void-accent text-void-accent"
                    : "border-transparent text-void-muted hover:text-void-text"
                  }
                `}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
                {tab === "resume" && !job.resume_text && " —"}
                {tab === "cover" && !job.cover_letter_text && " —"}
              </button>
            ))}
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
            <div className="p-5">
              {job.score_reasoning && (
                <div className="mb-5 p-3 rounded-lg bg-void-raised border border-void-border">
                  <p className="text-xs font-medium text-void-muted mb-1">Score Reasoning</p>
                  <p className="text-sm text-void-text leading-relaxed">{job.score_reasoning}</p>
                </div>
              )}
              {job.full_description ? (
                <pre className="text-xs text-void-muted whitespace-pre-wrap font-mono leading-relaxed">
                  {job.full_description}
                </pre>
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
                    disabled={generatingResume}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors"
                  >
                    {generatingResume ? (
                      <>
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Generating…
                      </>
                    ) : (
                      "Generate Tailored Resume"
                    )}
                  </button>
                </div>
              )}
            </div>
          )}

          {!loading && job && activeTab === "cover" && (
            <div className="p-5">
              {job.cover_letter_text ? (
                <pre className="text-sm text-void-text whitespace-pre-wrap leading-relaxed">
                  {job.cover_letter_text}
                </pre>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <p className="text-sm text-void-muted">No cover letter yet.</p>
                  <button
                    onClick={handleGenerateCover}
                    disabled={generatingCover}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors"
                  >
                    {generatingCover ? (
                      <>
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Generating…
                      </>
                    ) : (
                      "Generate Cover Letter"
                    )}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        {job && (
          <div className="flex items-center gap-2 p-4 border-t border-void-border shrink-0 flex-wrap">
            {activeTab === "resume" && job.resume_text && (
              editingResume ? (
                <>
                  <button
                    onClick={handleSaveResume}
                    disabled={saving}
                    className="px-4 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors"
                  >
                    {saving ? "Saving…" : "Save Resume"}
                  </button>
                  <button
                    onClick={() => { setEditingResume(false); setResumeText(job.resume_text!); }}
                    className="px-4 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text transition-colors"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => setEditingResume(true)}
                    className="px-4 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text transition-colors"
                  >
                    Edit
                  </button>
                  <button
                    onClick={handleGenerateResume}
                    disabled={generatingResume}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text disabled:opacity-50 transition-colors"
                  >
                    {generatingResume ? (
                      <>
                        <span className="w-3.5 h-3.5 border-2 border-void-muted/30 border-t-void-muted rounded-full animate-spin" />
                        Regenerating…
                      </>
                    ) : "Regenerate"}
                  </button>
                </>
              )
            )}

            {activeTab === "cover" && job.cover_letter_text && (
              <button
                onClick={handleGenerateCover}
                disabled={generatingCover}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text disabled:opacity-50 transition-colors"
              >
                {generatingCover ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-void-muted/30 border-t-void-muted rounded-full animate-spin" />
                    Regenerating…
                  </>
                ) : "Regenerate"}
              </button>
            )}

            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 px-3 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text transition-colors"
            >
              View Job
              <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                <path fillRule="evenodd" d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5Z" clipRule="evenodd"/>
                <path fillRule="evenodd" d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5Z" clipRule="evenodd"/>
              </svg>
            </a>
            {job.application_url && job.application_url !== job.url && (
              <a
                href={job.application_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 px-3 py-2 rounded-lg bg-void-accent/10 border border-void-accent/30 text-sm text-void-accent hover:bg-void-accent/20 transition-colors"
              >
                Apply Direct
                <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                  <path fillRule="evenodd" d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5Z" clipRule="evenodd"/>
                  <path fillRule="evenodd" d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5Z" clipRule="evenodd"/>
                </svg>
              </a>
            )}
            {job.has_pdf && (
              <a href={resumeUrl(job.url_encoded)} target="_blank" rel="noopener noreferrer"
                className="px-3 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text transition-colors">
                Download PDF
              </a>
            )}
            {job.has_cover_pdf && (
              <a href={coverUrl(job.url_encoded)} target="_blank" rel="noopener noreferrer"
                className="px-3 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text transition-colors">
                Cover PDF
              </a>
            )}

            <div className="ml-auto flex items-center gap-2">
              {job.apply_status === "dismissed" ? (
                <button onClick={() => restoreJob(job.url_encoded).then(onJobUpdated)}
                  className="px-3 py-2 rounded-lg border border-void-success/40 text-sm text-void-success hover:bg-void-success/10 transition-colors">
                  Restore
                </button>
              ) : (
                <button onClick={handleDismiss}
                  className="px-3 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-danger hover:border-void-danger/40 transition-colors">
                  Dismiss
                </button>
              )}

              {job.apply_status !== "applied" && (
                <button onClick={handleMarkApplied}
                  className="px-4 py-2 rounded-lg bg-void-success/15 border border-void-success/40 text-sm text-void-success hover:bg-void-success/25 transition-colors">
                  Mark Applied
                </button>
              )}

              {job.apply_status === "applied" && (
                <div className="flex gap-1">
                  {["interview", "offer", "rejected"].map((s) => (
                    <button key={s} onClick={() => handleMarkStatus(s)}
                      className="px-2.5 py-1.5 rounded border border-void-border text-xs text-void-muted hover:text-void-text transition-colors capitalize">
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
