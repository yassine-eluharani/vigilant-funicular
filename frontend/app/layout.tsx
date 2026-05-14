import type { Metadata } from "next";
import { Inter, Fraunces, JetBrains_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";
import { ToastProvider } from "@/components/ui/Toast";
import { AuthProvider } from "@/contexts/AuthContext";

// Body sans: Inter — high x-height, hinted for screens, the workhorse for
// dense UI text. Use the variable cut so weight can swing without loading
// extra files.
const inter = Inter({
  variable: "--font-sans-base",
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz"],
});

// Display serif: Fraunces — variable axes (weight + opsz + SOFT) give it
// real character at headline sizes without going anaemic on dark
// backgrounds the way the previous Instrument Serif did at weight 400.
const fraunces = Fraunces({
  variable: "--font-display-base",
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz", "SOFT"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono-base",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "ApplyPilot — AI-Powered Job Applications",
  description: "Discover, score, tailor, and auto-submit job applications with AI. Apply to 100+ jobs overnight.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <ClerkProvider
      signInUrl="/login"
      signUpUrl="/register"
      publishableKey={
        // Fall back to a syntactically valid dummy during build so Clerk's
        // key check doesn't crash `next build` when the real key isn't set
        // (e.g. in CI without secrets, or local docker builds). The key is
        // base64("build-dummy.clerk.accounts.dev$") and is not a real account.
        // `||` (not `??`) so empty-string env vars also fall back — Docker
        // build-args evaluate undefined ARGs to "" rather than leaving them
        // unset, which slipped past `??` and crashed Clerk in publish.yml.
        process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ||
        "pk_test_YnVpbGQtZHVtbXkuY2xlcmsuYWNjb3VudHMuZGV2JA"
      }
    >
      <html
        lang="en"
        className={`${inter.variable} ${fraunces.variable} ${jetbrainsMono.variable} h-full`}
      >
        <body className="h-full bg-void-bg text-void-text antialiased font-sans">
          <AuthProvider>
            <ToastProvider>
              {children}
            </ToastProvider>
          </AuthProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
