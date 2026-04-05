"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { login, isAuthenticated, isLoading } = useAuth();

  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // If already authenticated, redirect
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace(params.get("next") ?? "/jobs");
    }
  }, [isAuthenticated, isLoading, router, params]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    const result = await login(password);
    setSubmitting(false);
    if (!result.ok) {
      setError(result.error ?? "Incorrect password");
      return;
    }
    // Check if first-time setup needed (profile has no name)
    try {
      const res = await fetch(
        (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/profile",
        { headers: { Authorization: `Bearer ${localStorage.getItem("ap_token")}` } }
      );
      if (res.ok) {
        const profile = await res.json();
        if (!profile?.personal?.full_name) {
          router.replace("/setup");
          return;
        }
      }
    } catch { /* ignore — go to jobs anyway */ }
    router.replace(params.get("next") ?? "/jobs");
  };

  if (isLoading) return null;

  return (
    <div className="min-h-screen flex items-center justify-center bg-void-bg px-4">
      <div className="w-full max-w-sm">
        {/* Logo / branding */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-void-accent/10 border border-void-accent/30 flex items-center justify-center mb-4">
            <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6 text-void-accent" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 0 0 .75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 0 0-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0 1 12 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 0 1-.673-.38m0 0A2.18 2.18 0 0 1 3 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 0 1 3.413-.387m7.5 0V5.25A2.25 2.25 0 0 0 13.5 3h-3a2.25 2.25 0 0 0-2.25 2.25v.894m7.5 0a48.667 48.667 0 0 0-7.5 0" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-void-text">ApplyPilot</h1>
          <p className="text-sm text-void-muted mt-1">AI-powered job application pipeline</p>
        </div>

        {/* Login card */}
        <div className="bg-void-surface border border-void-border rounded-2xl p-6">
          <h2 className="text-sm font-medium text-void-text mb-4">Sign in</h2>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="text-xs text-void-muted block mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoFocus
                required
                className="w-full px-3 py-2.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors"
              />
            </div>

            {error && (
              <p className="text-xs text-void-danger bg-void-danger/10 border border-void-danger/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting || !password}
              className="w-full py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
            >
              {submitting ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin-slow" />
              ) : "Sign in"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-void-subtle mt-6">
          Set <code className="font-mono bg-void-raised px-1.5 py-0.5 rounded text-void-muted">APP_PASSWORD</code> in your <code className="font-mono bg-void-raised px-1.5 py-0.5 rounded text-void-muted">.env</code> file
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
