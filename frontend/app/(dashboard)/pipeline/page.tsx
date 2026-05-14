"use client";

/**
 * Pipeline visibility page — read-only funnel + score distribution.
 *
 * Scoring + tailoring run on the discovery worker (separate repo, on the
 * homelab) every ~2h. There is no client-side trigger to fire here
 * anymore; this page exists to show the user where jobs are in the
 * funnel between discovery and "ready to apply".
 */

import { ScoreDistributionChart } from "@/components/pipeline/ScoreDistributionChart";
import { FunnelChart } from "@/components/pipeline/FunnelChart";
import { useStats } from "@/lib/hooks/useStats";

export default function PipelinePage() {
  const { stats } = useStats();
  const loading = stats === null;

  return (
    <main className="page-accent-pipeline flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
        <header>
          <p className="text-xs text-void-muted font-medium uppercase tracking-wider mb-1">
            Pipeline
          </p>
          <h1 className="font-display text-3xl text-void-text leading-tight">
            Where your jobs are
          </h1>
          <p className="text-sm text-void-muted mt-2 max-w-2xl">
            The discovery worker on the homelab runs every ~2 hours. It
            scrapes Gulf-remote postings, scores them against your CV, and
            auto-generates tailored docs for any 9–10 fit. Lower-scored jobs
            wait for you to tailor manually from the Archive.
          </p>
        </header>

        {loading || !stats ? (
          <div className="text-sm text-void-muted">Loading…</div>
        ) : (
          <>
            <section className="bg-void-surface border border-void-border rounded-xl p-6">
              <h2 className="text-xs font-medium text-void-muted uppercase tracking-wider mb-4">
                Funnel
              </h2>
              <FunnelChart funnel={stats.funnel} />
            </section>

            {stats.score_distribution && (
              <section className="bg-void-surface border border-void-border rounded-xl p-6">
                <h2 className="text-xs font-medium text-void-muted uppercase tracking-wider mb-4">
                  Score distribution
                </h2>
                <ScoreDistributionChart
                  distribution={stats.score_distribution}
                  scored={stats.funnel.scored}
                  pending={stats.funnel.pending_score}
                />
              </section>
            )}
          </>
        )}
      </div>
    </main>
  );
}
