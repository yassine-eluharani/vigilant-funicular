"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="text-center max-w-sm">
        <p className="text-4xl font-bold font-mono text-void-danger mb-4">500</p>
        <h1 className="text-xl font-semibold text-void-text mb-2">Something went wrong</h1>
        <p className="text-sm text-void-muted mb-8">
          An unexpected error occurred. Try refreshing the page.
        </p>
        <button
          onClick={reset}
          className="px-5 py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
