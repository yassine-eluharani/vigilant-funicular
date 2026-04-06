"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setSubmitting(true);
    const result = await register(fullName, email, password);
    setSubmitting(false);
    if (!result.ok) {
      setError(result.error ?? "Registration failed");
      return;
    }
    // New user → go to setup wizard
    router.replace("/setup");
  };

  return (
    <div className="min-h-screen flex">
      {/* Left branding panel */}
      <div className="hidden lg:flex flex-col justify-between w-[45%] bg-void-surface border-r border-void-border p-12 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[400px] h-[400px] bg-void-success/6 rounded-full blur-[100px]" />
        </div>
        <Link href="/" className="relative flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-void-accent flex items-center justify-center">
            <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
              <path fillRule="evenodd" d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z" clipRule="evenodd" />
            </svg>
          </div>
          <span className="font-semibold text-void-text">ApplyPilot</span>
        </Link>

        <div className="relative space-y-6">
          {[
            { icon: "🔍", title: "Discover 200+ jobs", desc: "Across all major boards and Workday portals" },
            { icon: "🤖", title: "AI scores every role", desc: "1–10 fit score against your profile, instantly" },
            { icon: "📄", title: "Tailored resume + cover", desc: "Generated per job, validated, exported to PDF" },
            { icon: "🚀", title: "Auto-submit overnight", desc: "Browser workers apply while you sleep" },
          ].map(({ icon, title, desc }) => (
            <div key={title} className="flex items-start gap-3">
              <span className="text-xl">{icon}</span>
              <div>
                <p className="text-sm font-medium text-void-text">{title}</p>
                <p className="text-xs text-void-muted">{desc}</p>
              </div>
            </div>
          ))}
        </div>

        <p className="relative text-xs text-void-subtle">© 2026 ApplyPilot. All rights reserved.</p>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <Link href="/" className="flex lg:hidden items-center gap-2 mb-8">
            <div className="w-7 h-7 rounded-lg bg-void-accent flex items-center justify-center">
              <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
                <path fillRule="evenodd" d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z" clipRule="evenodd" />
              </svg>
            </div>
            <span className="font-semibold text-void-text text-sm">ApplyPilot</span>
          </Link>

          <h1 className="text-2xl font-bold text-void-text mb-1">Create your account</h1>
          <p className="text-sm text-void-muted mb-8">
            Already have an account?{" "}
            <Link href="/login" className="text-void-accent hover:underline">Sign in</Link>
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="text-xs text-void-muted block mb-1.5">Full name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Jane Smith"
                required
                autoFocus
                className="w-full px-3 py-2.5 rounded-lg bg-void-surface border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors"
              />
            </div>

            <div>
              <label className="text-xs text-void-muted block mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="w-full px-3 py-2.5 rounded-lg bg-void-surface border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors"
              />
            </div>

            <div>
              <label className="text-xs text-void-muted block mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min. 8 characters"
                required
                className="w-full px-3 py-2.5 rounded-lg bg-void-surface border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors"
              />
            </div>

            {error && (
              <p className="text-xs text-void-danger bg-void-danger/10 border border-void-danger/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting || !fullName || !email || !password}
              className="w-full py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 mt-1"
            >
              {submitting
                ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin-slow" />
                : "Create account →"}
            </button>

            <p className="text-center text-xs text-void-subtle">
              By signing up you agree to store your data locally on your server.
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
