"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { JobCard } from "@/components/jobs/JobCard";
import { JobFilters, type Filters } from "@/components/jobs/JobFilters";
import { JobDetailDrawer } from "@/components/jobs/JobDetailDrawer";
import { useJobs } from "@/lib/hooks/useJobs";
import { useStats } from "@/lib/hooks/useStats";
import { dismissJob, markApplied } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import type { Job } from "@/lib/types";

const DEFAULT_FILTERS: Filters = {
  minScore: 7,
  maxScore: 10,
  site: "",
  search: "",
  status: "pending",
};

function SkeletonCard() {
  return (
    <div className="bg-void-surface border border-void-border rounded-lg p-4 flex flex-col gap-3">
      <div className="flex gap-3">
        <div className="skeleton w-9 h-9 rounded-lg" />
        <div className="flex-1 space-y-2">
          <div className="skeleton h-4 w-3/4" />
          <div className="skeleton h-3 w-1/2" />
        </div>
        <div className="skeleton w-8 h-8 rounded-full" />
      </div>
      <div className="skeleton h-3 w-full" />
      <div className="skeleton h-3 w-2/3" />
      <div className="skeleton h-8 w-full rounded mt-1" />
    </div>
  );
}

export default function JobsPage() {
  const toast = useToast();
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);
  const { jobs, total, loading, loadingMore, hasMore, loadMore, refresh } = useJobs(filters);
  const { stats } = useStats();

  // Infinite scroll sentinel
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sentinelRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) loadMore(); },
      { threshold: 0.1 }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [loadMore]);

  const handleDismiss = useCallback(async (job: Job) => {
    try {
      await dismissJob(job.url_encoded);
      toast("Job dismissed");
      refresh();
    } catch {
      toast("Failed to dismiss", false);
    }
  }, [toast, refresh]);

  const handleMarkApplied = useCallback(async (job: Job) => {
    try {
      await markApplied(job.url_encoded);
      toast("Marked as applied");
      refresh();
    } catch {
      toast("Failed to update status", false);
    }
  }, [toast, refresh]);

  return (
    <div className="flex h-full">
      {/* Sidebar filters */}
      <aside className="w-56 shrink-0 border-r border-void-border bg-void-surface overflow-y-auto">
        {stats && (
          <div className="px-4 pt-4 pb-2 border-b border-void-border">
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: "Tailored",  value: stats.tailored  },
                { label: "Applied",   value: stats.applied   },
                { label: "Ready",     value: stats.ready_to_apply },
                { label: "Dismissed", value: stats.dismissed },
              ].map(({ label, value }) => (
                <div key={label} className="bg-void-raised rounded-lg px-2 py-2 text-center border border-void-border">
                  <p className="text-lg font-semibold font-mono text-void-text">{value}</p>
                  <p className="text-xs text-void-muted">{label}</p>
                </div>
              ))}
            </div>
          </div>
        )}
        <JobFilters
          filters={filters}
          sites={stats?.sites ?? []}
          onChange={setFilters}
        />
      </aside>

      {/* Main content */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-void-border shrink-0">
          <div>
            <h1 className="text-base font-semibold text-void-text">Jobs</h1>
            {!loading && (
              <p className="text-xs text-void-muted mt-0.5">
                {total} job{total !== 1 ? "s" : ""} · showing {jobs.length}
              </p>
            )}
          </div>
          <button
            onClick={refresh}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-void-border text-xs text-void-muted hover:text-void-text transition-colors"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <path fillRule="evenodd" d="M13.887 5.923a.5.5 0 0 1 .123.52l-1.5 4.5a.5.5 0 0 1-.88.143l-1.54-2.31-1.677 1.676a.5.5 0 0 1-.707 0L6.146 8.896 4.177 11.5a.5.5 0 0 1-.854-.354V8.5H2a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 .5.5v1.793L7.146 4.146a.5.5 0 0 1 .708 0l1.56 1.56 1.677-1.676a.5.5 0 0 1 .52-.123l2.276.016Z" clipRule="evenodd"/>
            </svg>
            Refresh
          </button>
        </div>

        {/* Job grid */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Array.from({ length: 9 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-void-muted">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-12 h-12 mb-3 opacity-40">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
              </svg>
              <p className="text-sm">No jobs match your filters</p>
              <button onClick={() => setFilters(DEFAULT_FILTERS)} className="text-xs text-void-accent mt-2 hover:underline">
                Reset filters
              </button>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {jobs.map((job) => (
                  <JobCard
                    key={job.url}
                    job={job}
                    onSelect={(j) => setSelectedUrl(j.url_encoded)}
                    onDismiss={handleDismiss}
                    onMarkApplied={handleMarkApplied}
                  />
                ))}
              </div>
              {hasMore && (
                <div ref={sentinelRef} className="py-6 flex justify-center">
                  {loadingMore && (
                    <div className="w-5 h-5 border-2 border-void-border border-t-void-accent rounded-full animate-spin-slow" />
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Detail Drawer */}
      <JobDetailDrawer
        encodedUrl={selectedUrl}
        onClose={() => setSelectedUrl(null)}
        onJobUpdated={refresh}
      />
    </div>
  );
}
