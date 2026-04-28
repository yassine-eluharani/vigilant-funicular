import type { Metadata } from "next";
import { Geist, Instrument_Serif, JetBrains_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";
import { ToastProvider } from "@/components/ui/Toast";
import { AuthProvider } from "@/contexts/AuthContext";

const geist = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
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
        process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ??
        "pk_test_YnVpbGQtZHVtbXkuY2xlcmsuYWNjb3VudHMuZGV2JA"
      }
    >
      <html
        lang="en"
        className={`${geist.variable} ${instrumentSerif.variable} ${jetbrainsMono.variable} h-full`}
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
