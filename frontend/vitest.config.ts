import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vitest config for the ApplyPilot frontend (TST-025).
//
// We keep this minimal on purpose — tests are unit-scope component tests
// (Toast, ScoreBadge, etc.). No SSR, no server actions, no `next/font`
// transformer. If we ever need those, switch to `@vitejs/plugin-react-swc`
// or wire `next/jest`-style mocks here.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Mirror the `@/*` paths from tsconfig so test imports work the
      // same way component imports do at runtime.
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // Keep tests collocated with components under __tests__/ folders to
    // avoid drift between source tree and test discovery.
    include: ["**/__tests__/**/*.{test,spec}.{ts,tsx}"],
    css: false,
  },
});
