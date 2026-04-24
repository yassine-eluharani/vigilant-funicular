import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="text-center">
        <p className="text-6xl font-bold font-mono text-void-accent mb-4">404</p>
        <h1 className="text-xl font-semibold text-void-text mb-2">Page not found</h1>
        <p className="text-sm text-void-muted mb-8">The page you&apos;re looking for doesn&apos;t exist.</p>
        <Link
          href="/jobs"
          className="px-5 py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 transition-colors"
        >
          Back to jobs
        </Link>
      </div>
    </div>
  );
}
