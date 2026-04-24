"use client";

import { Suspense } from "react";
import { SignIn } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

function LoginPanel() {
  const params = useSearchParams();
  const next = params.get("next") ?? "/jobs";

  return (
    <div className="min-h-screen flex">
      {/* Left panel — branding */}
      <div className="hidden lg:flex flex-col justify-between w-[45%] bg-void-surface border-r border-void-border p-12 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute bottom-1/4 left-1/2 -translate-x-1/2 w-[400px] h-[400px] bg-void-accent/8 rounded-full blur-[100px]" />
        </div>
        <Link href="/" className="relative flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-void-accent flex items-center justify-center">
            <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
              <path fillRule="evenodd" d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z" clipRule="evenodd" />
            </svg>
          </div>
          <span className="font-semibold text-void-text">ApplyPilot</span>
        </Link>

        <div className="relative">
          <blockquote className="text-xl font-medium text-void-text leading-relaxed mb-6">
            &ldquo;Scored 200 jobs against my profile in minutes. Tailored resume ready before I even finished my coffee.&rdquo;
          </blockquote>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-void-accent/20 border border-void-accent/30 flex items-center justify-center text-sm font-bold text-void-accent">Y</div>
            <div>
              <p className="text-sm font-medium text-void-text">Yassine E.</p>
              <p className="text-xs text-void-muted">Software Engineer</p>
            </div>
          </div>
        </div>

        <p className="relative text-xs text-void-subtle">© 2026 ApplyPilot. All rights reserved.</p>
      </div>

      {/* Right panel — Clerk SignIn */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        {/* Mobile logo */}
        <div className="w-full max-w-sm flex flex-col items-center gap-8">
          <Link href="/" className="flex lg:hidden items-center gap-2 self-start">
            <div className="w-7 h-7 rounded-lg bg-void-accent flex items-center justify-center">
              <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
                <path fillRule="evenodd" d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z" clipRule="evenodd" />
              </svg>
            </div>
            <span className="font-semibold text-void-text text-sm">ApplyPilot</span>
          </Link>

          <SignIn
            forceRedirectUrl={next}
            signUpUrl="/register"
            appearance={{
              variables: {
                colorPrimary: "#6366f1",
                colorBackground: "#0d0d1a",
                colorInputBackground: "#13131f",
                colorText: "#e2e8f0",
                colorTextSecondary: "#94a3b8",
                colorInputText: "#e2e8f0",
                colorNeutral: "#1e1e30",
                borderRadius: "0.5rem",
                fontFamily: "var(--font-inter), sans-serif",
              },
              elements: {
                card: "shadow-none border border-white/[0.06] bg-[#0d0d1a]",
                headerTitle: "text-void-text",
                headerSubtitle: "text-void-muted",
                formButtonPrimary: "bg-void-accent hover:bg-indigo-500 text-white text-sm",
                formFieldInput: "bg-[#13131f] border-white/10 text-void-text",
                footerActionLink: "text-void-accent hover:text-indigo-400",
                dividerLine: "bg-white/10",
                dividerText: "text-void-subtle",
                socialButtonsBlockButton: "border-white/10 text-void-text hover:bg-white/5",
                identityPreviewEditButton: "text-void-accent",
              },
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginPanel />
    </Suspense>
  );
}
