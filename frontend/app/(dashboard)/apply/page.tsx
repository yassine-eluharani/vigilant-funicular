"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { JobCard } from "@/components/jobs/JobCard";
import { JobDetailDrawer } from "@/components/jobs/JobDetailDrawer";
import {
  getJobs,
  getJob,
  dismissJob,
  markApplied,
  downloadResume,
  downloadCover,
  getMe,
} from "@/lib/api";
import { ScoreBadge } from "@/components/jobs/ScoreBadge";
import { useToast } from "@/components/ui/Toast";
import type { Job, UserInfo } from "@/lib/types";

const READY_LIMIT = 20;
const CANDIDATES_LIMIT = 30;
const PREVIEW_LINES = 12;

type ReadyJob = Job & {
  resume_text?: string;
  cover_letter_text?: string;
};

function ReadyCard({
  job,
  onOpen,
  onMarkApplied,
  onDismiss,
}: {
  job: ReadyJob;
  onOpen: (job: Job) => void;
  onMarkApplied: (job: Job) => void;
  onDismiss: (job: Job) => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState<"applied" | "dismiss" | null>(null);
  const [resumeExpanded, setResumeExpanded] = useState(false);
  const [coverExpanded, setCoverExpanded] = useState(false);

  const resumeText = (job.resume_text ?? "").trim();
  const coverText = (job.cover_letter_text ?? "").trim();

  const applyHref = job.application_url && job.application_url !== job.url
    ? job.application_url
    : job.url;

  const handleDownloadResume = useCallback(async () => {
    try { await downloadResume(job.url_encoded, job.title); }
    catch { toast("Resume download failed", false); }
  }, [job.url_encoded, job.title, toast]);

  const handleDownloadCover = useCallback(async () => {
    try { await downloadCover(job.url_encoded, job.title); }
    catch { toast("Cover letter download failed", false); }
  }, [job.url_encoded, job.title, toast]);

  const handleApplied = async () => {
    setBusy("applied");
    try { onMarkApplied(job); } finally { setBusy(null); }
  };
  const handleDismiss = async () => {
    setBusy("dismiss");
    try { onDismiss(job); } finally { setBusy(null); }
  };

  return (
    <article className="bg-void-surface border border-void-border rounded-xl overflow-hidden hover:border-void-accent/30 transition-colors animate-fade-in">
      {/* Header */}
      <header className="flex items-start gap-4 p-5 border-b border-void-border">
        <ScoreBadge score={job.fit_score} size="lg" />
        <div className="flex-1 min-w-0">
          <h3 className="font-display text-xl text-void-text leading-snug truncate">
            {job.title}
          </h3>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-void-muted mt-1">
            {job.company && <span className="text-void-text">{job.company}</span>}
            {job.location && <span>· {job.location}</span>}
            {job.site && <span className="text-void-subtle">· {job.site}</span>}
          </div>
          {job.score_reasoning && (
            <p className="text-sm text-void-muted mt-2 line-clamp-2">
              {job.score_reasoning}
            </p>
          )}
        </div>
      </header>

      {/* Two-column inline preview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-void-border">
        <DocPreview
          label="Tailored CV"
          text={resumeText}
          expanded={resumeExpanded}
          onToggle={() => setResumeExpanded((v) => !v)}
          onDownload={handleDownloadResume}
        />
        <DocPreview
          label="Cover letter"
          text={coverText}
          expanded={coverExpanded}
          onToggle={() => setCoverExpanded((v) => !v)}
          onDownload={handleDownloadCover}
        />
      </div>

      {/* Actions */}
      <footer className="flex flex-wrap items-center gap-2 p-4 border-t border-void-border bg-void-bg/40">
        <a
          href={applyHref}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => onMarkApplied(job)}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-void-accent-hover transition-colors"
        >
          Apply on company site
          <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
            <path d="M6.22 4.22a.75.75 0 0 1 1.06 0l3.25 3.25a.75.75 0 0 1 0 1.06L7.28 11.78a.75.75 0 1 1-1.06-1.06L8.94 8 6.22 5.28a.75.75 0 0 1 0-1.06Z"/>
          </svg>
        </a>
        <button
          onClick={() => onOpen(job)}
          className="px-3 py-2 rounded-lg border border-void-border text-sm text-void-muted hover:text-void-text hover:border-void-accent/30 transition-colors"
        >
          Open detail
        </button>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={handleApplied}
            disabled={busy === "applied"}
            className="px-3 py-2 rounded-lg border border-void-success/30 text-sm text-void-success hover:bg-void-success/10 transition-colors disabled:opacity-50"
          >
            {busy === "applied" ? "Saving…" : "Mark applied"}
          </button>
          <button
            onClick={handleDismiss}
            disabled={busy === "dismiss"}
            className="px-3 py-2 rounded-lg text-sm text-void-subtle hover:text-void-danger hover:bg-void-danger/10 transition-colors disabled:opacity-50"
          >
            Dismiss
          </button>
        </div>
      </footer>
    </article>
  );
}

function DocPreview({
  label,
  text,
  expanded,
  onToggle,
  onDownload,
}: {
  label: string;
  text: string;
  expanded: boolean;
  onToggle: () => void;
  onDownload: () => void;
}) {
  const allLines = text.split("\n");
  const visible = expanded ? allLines : allLines.slice(0, PREVIEW_LINES);
  const truncated = !expanded && allLines.length > PREVIEW_LINES;

  return (
    <section className="p-4 min-w-0 flex flex-col">
      <header className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-medium uppercase tracking-wider text-void-subtle">
          {label}
        </h4>
        <button
          onClick={onDownload}
          className="text-xs text-void-muted hover:text-void-accent transition-colors"
          title={`Download ${label.toLowerCase()} as PDF`}
        >
          Download PDF
        </button>
      </header>
      <pre className="text-xs leading-relaxed text-void-text whitespace-pre-wrap break-words font-sans flex-1">
        {visible.join("\n")}
        {truncated && <span className="text-void-subtle">…</span>}
      </pre>
      {allLines.length > PREVIEW_LINES && (
        <button
          onClick={onToggle}
          className="mt-2 text-xs text-void-accent hover:underline self-start"
        >
          {expanded ? "Collapse" : `Expand (${allLines.length} lines)`}
        </button>
      )}
    </section>
  );
}

function ReadySkeleton() {
  return (
    <div className="bg-void-surface border border-void-border rounded-xl overflow-hidden animate-pulse">
      <div className="p-5 flex items-start gap-4 border-b border-void-border">
        <div className="w-12 h-12 rounded-full bg-void-raised" />
        <div className="flex-1 space-y-2">
          <div className="h-5 w-2/3 rounded bg-void-raised" />
          <div className="h-3 w-1/2 rounded bg-void-raised" />
          <div className="h-3 w-3/4 rounded bg-void-raised" />
        </div>
      </div>
      <div className="grid grid-cols-2 divide-x divide-void-border">
        {[0, 1].map((i) => (
          <div key={i} className="p-4 space-y-1.5">
            <div className="h-3 w-24 rounded bg-void-raised mb-2" />
            {Array.from({ length: 8 }).map((_, j) => (
              <div key={j} className="h-2.5 rounded bg-void-raised" style={{ width: `${50 + ((j * 13) % 50)}%` }} />
            ))}
          </div>
        ))}
      </div>
      <div className="p-4 flex gap-2 border-t border-void-border">
        <div className="h-9 w-44 rounded bg-void-raised" />
        <div className="h-9 w-24 rounded bg-void-raised" />
      </div>
    </div>
  );
}

function ApplyPanel() {
  const toast = useToast();
  const [me, setMe] = useState<UserInfo | null>(null);
  const [readyJobs, setReadyJobs] = useState<ReadyJob[]>([]);
  const [readyLoading, setReadyLoading] = useState(true);
  const [pendingHigh, setPendingHigh] = useState(0);
  const [candidates, setCandidates] = useState<Job[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(true);
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);
  const [candidatesOpen, setCandidatesOpen] = useState(false);

  const refresh = useCallback(async () => {
    setReadyLoading(true);
    setCandidatesLoading(true);
    try {
      // Top section threshold matches the discovery worker's
      // AUTO_TAILOR_MIN_SCORE (default 8). Anything ≥ 8 gets auto-docs;
      // 9-10 still float to the top via fit_score DESC ordering.
      const [topResp, midResp] = await Promise.all([
        getJobs({ min_score: 8, max_score: 10, status: "scored", limit: READY_LIMIT }),
        getJobs({ min_score: 7, max_score: 7, status: "scored", limit: CANDIDATES_LIMIT }),
      ]);

      // Split top into "ready" (has both docs) vs "still generating".
      const readyList = topResp.jobs.filter(j => j.has_pdf && j.has_cover_pdf);
      setPendingHigh(topResp.jobs.length - readyList.length);
      setCandidates(midResp.jobs);

      // Fetch full text for ready jobs (resume_text + cover_letter_text are
      // detail-only fields). Done in parallel — small bounded set.
      const detailed = await Promise.all(
        readyList.map(async (j) => {
          try {
            const detail = await getJob(j.url_encoded);
            return { ...j, resume_text: detail.resume_text, cover_letter_text: detail.cover_letter_text };
          } catch {
            return j as ReadyJob;
          }
        })
      );
      setReadyJobs(detailed);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to load jobs", false);
    } finally {
      setReadyLoading(false);
      setCandidatesLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    let cancelled = false;
    getMe().then((u) => { if (!cancelled) setMe(u); }).catch(() => null);
    refresh();
    // Scoring + auto-tailor are owned by the discovery worker (runs every
    // 2h on the homelab), so there's no client-side trigger to fire here.
    return () => { cancelled = true; };
  }, [refresh]);

  const handleMarkApplied = useCallback(async (job: Job) => {
    try {
      await markApplied(job.url_encoded);
      toast("Marked as applied");
      refresh();
    } catch {
      toast("Failed to mark applied", false);
    }
  }, [toast, refresh]);

  const handleDismiss = useCallback(async (job: Job) => {
    try {
      await dismissJob(job.url_encoded);
      toast("Job dismissed");
      refresh();
    } catch {
      toast("Failed to dismiss", false);
    }
  }, [toast, refresh]);

  const showSetupPrompt = me && !me.has_profile;

  return (
    <main className="page-accent-jobs flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Header */}
        <header className="mb-8">
          <p className="text-xs text-void-muted font-medium uppercase tracking-wider mb-1">
            Today
          </p>
          <h1 className="font-display text-3xl text-void-text leading-tight">
            Ready to apply
          </h1>
          <p className="text-sm text-void-muted mt-2">
            High-fit jobs (8+) with a tailored CV and cover letter waiting for you.
          </p>
        </header>

        {showSetupPrompt && (
          <div className="mb-6 flex items-center gap-3 p-3 rounded-lg border border-void-accent/30 bg-void-accent/5">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-void-accent shrink-0">
              <path fillRule="evenodd" d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Zm-7-4a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM9 9a.75.75 0 0 0 0 1.5h.253a.25.25 0 0 1 .244.304l-.459 2.066A1.75 1.75 0 0 0 10.747 15H11a.75.75 0 0 0 0-1.5h-.253a.25.25 0 0 1-.244-.304l.459-2.066A1.75 1.75 0 0 0 9.253 9H9Z" clipRule="evenodd" />
            </svg>
            <p className="text-sm text-void-muted flex-1">
              Complete your profile so jobs can be scored against your CV.
            </p>
            <a href="/setup" className="text-xs font-medium text-void-accent hover:underline shrink-0">
              Set up now →
            </a>
          </div>
        )}

        {/* Ready section */}
        {readyLoading ? (
          <div className="space-y-5">
            {Array.from({ length: 2 }).map((_, i) => <ReadySkeleton key={i} />)}
          </div>
        ) : readyJobs.length === 0 ? (
          <EmptyReady pendingHigh={pendingHigh} />
        ) : (
          <div className="space-y-5">
            {readyJobs.map((job) => (
              <ReadyCard
                key={job.url}
                job={job}
                onOpen={(j) => setSelectedUrl(j.url_encoded)}
                onMarkApplied={handleMarkApplied}
                onDismiss={handleDismiss}
              />
            ))}
            {pendingHigh > 0 && (
              <p className="text-xs text-void-subtle text-center pt-2">
                {pendingHigh} more high-fit job{pendingHigh > 1 ? "s" : ""} still being prepared…
              </p>
            )}
          </div>
        )}

        {/* Candidates section */}
        <section className="mt-12">
          <button
            onClick={() => setCandidatesOpen((v) => !v)}
            className="flex items-center gap-2 text-sm text-void-muted hover:text-void-text transition-colors"
          >
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className={`w-4 h-4 transition-transform ${candidatesOpen ? "rotate-90" : ""}`}
            >
              <path d="M6 4l8 6-8 6V4z" />
            </svg>
            <span className="font-display text-lg text-void-text">
              More candidates
            </span>
            <span className="text-xs text-void-subtle">
              7 score · {candidatesLoading ? "loading…" : `${candidates.length} job${candidates.length === 1 ? "" : "s"}`}
            </span>
          </button>

          {candidatesOpen && (
            <div className="mt-5">
              {candidatesLoading ? (
                <p className="text-sm text-void-subtle">Loading…</p>
              ) : candidates.length === 0 ? (
                <p className="text-sm text-void-subtle">Nothing scoring 7 right now.</p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {candidates.map((job) => (
                    <JobCard
                      key={job.url}
                      job={job}
                      onSelect={(j) => setSelectedUrl(j.url_encoded)}
                      onDismiss={handleDismiss}
                      onMarkApplied={handleMarkApplied}
                      onRefresh={refresh}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      <JobDetailDrawer
        encodedUrl={selectedUrl}
        onClose={() => setSelectedUrl(null)}
        onJobUpdated={refresh}
      />
    </main>
  );
}

function EmptyReady({ pendingHigh }: { pendingHigh: number }) {
  return (
    <div className="bg-void-surface border border-void-border rounded-xl p-8 text-center">
      <p className="font-display text-xl text-void-text mb-2">
        {pendingHigh > 0 ? "Almost ready" : "Nothing yet"}
      </p>
      <p className="text-sm text-void-muted max-w-md mx-auto">
        {pendingHigh > 0
          ? `${pendingHigh} high-fit job${pendingHigh > 1 ? "s are" : " is"} being prepared. Tailored CV + cover letter generation runs in the background.`
          : "No 8+ scored jobs with documents yet. Scoring runs in the background as the discovery worker finds new postings — check back shortly or browse the archive."}
      </p>
      <a
        href="/jobs"
        className="inline-block mt-5 text-xs font-medium text-void-accent hover:underline"
      >
        Browse all jobs in the archive →
      </a>
    </div>
  );
}

export default function ApplyPage() {
  return (
    <Suspense>
      <ApplyPanel />
    </Suspense>
  );
}
