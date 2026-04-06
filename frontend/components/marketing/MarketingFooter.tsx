import Link from "next/link";

export function MarketingFooter() {
  return (
    <footer className="border-t border-void-border/60 bg-void-surface/40">
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-7 h-7 rounded-lg bg-void-accent flex items-center justify-center">
                <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
                  <path fillRule="evenodd" d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z" clipRule="evenodd" />
                </svg>
              </div>
              <span className="text-sm font-semibold text-void-text">ApplyPilot</span>
            </div>
            <p className="text-xs text-void-muted leading-relaxed">
              AI-powered job application automation. Discover, score, tailor, and apply — overnight.
            </p>
          </div>

          {/* Product */}
          <div>
            <p className="text-xs font-semibold text-void-text uppercase tracking-wider mb-3">Product</p>
            <div className="flex flex-col gap-2">
              <Link href="/#features" className="text-sm text-void-muted hover:text-void-text transition-colors">Features</Link>
              <Link href="/#how-it-works" className="text-sm text-void-muted hover:text-void-text transition-colors">How it works</Link>
              <Link href="/pricing" className="text-sm text-void-muted hover:text-void-text transition-colors">Pricing</Link>
            </div>
          </div>

          {/* Account */}
          <div>
            <p className="text-xs font-semibold text-void-text uppercase tracking-wider mb-3">Account</p>
            <div className="flex flex-col gap-2">
              <Link href="/register" className="text-sm text-void-muted hover:text-void-text transition-colors">Sign up free</Link>
              <Link href="/login" className="text-sm text-void-muted hover:text-void-text transition-colors">Sign in</Link>
              <Link href="/jobs" className="text-sm text-void-muted hover:text-void-text transition-colors">Dashboard</Link>
            </div>
          </div>

          {/* Tech */}
          <div>
            <p className="text-xs font-semibold text-void-text uppercase tracking-wider mb-3">Stack</p>
            <div className="flex flex-col gap-2">
              <span className="text-sm text-void-muted">Python · FastAPI</span>
              <span className="text-sm text-void-muted">Next.js · Tailwind</span>
              <span className="text-sm text-void-muted">Playwright · LLM</span>
            </div>
          </div>
        </div>

        <div className="border-t border-void-border/40 pt-6 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-xs text-void-subtle">© 2026 ApplyPilot. All rights reserved.</p>
          <p className="text-xs text-void-subtle font-mono">v1.0.0</p>
        </div>
      </div>
    </footer>
  );
}
