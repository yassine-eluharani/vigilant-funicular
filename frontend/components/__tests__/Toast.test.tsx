/**
 * Toast component smoke tests (TST-025).
 *
 * Two purposes:
 *   1. Prove the Vitest + React Testing Library + jsdom harness boots and
 *      can render a real component from this codebase.
 *   2. Pin the contract that `useToast()` returns a `toast(text, ok)`
 *      function whose calls render a banner that auto-dismisses after the
 *      module's setTimeout fires.
 *
 * We don't try to assert on Tailwind classes or animation timing — those
 * are visual concerns. We assert on what a user sees: text appears, then
 * disappears.
 */

import "@testing-library/jest-dom/vitest";

import { act, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ToastProvider, useToast } from "../ui/Toast";

/**
 * Test harness: a button that calls `toast(...)` when clicked, mounted
 * inside `ToastProvider`. Lets us drive the hook from outside React.
 */
function Trigger({ text, ok }: { text: string; ok?: boolean }) {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() => toast(text, ok)}
      data-testid="trigger"
    >
      fire
    </button>
  );
}

describe("Toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  test("renders a message when toast() is called", () => {
    render(
      <ToastProvider>
        <Trigger text="Hello, world" />
      </ToastProvider>,
    );

    // Nothing visible yet — the toast list is empty.
    expect(screen.queryByText("Hello, world")).not.toBeInTheDocument();

    // Click the trigger inside `act` so the state update flushes.
    act(() => {
      screen.getByTestId("trigger").click();
    });

    expect(screen.getByText("Hello, world")).toBeInTheDocument();
  });

  test("dismisses the message after 3500ms", () => {
    render(
      <ToastProvider>
        <Trigger text="Bye, world" />
      </ToastProvider>,
    );

    act(() => {
      screen.getByTestId("trigger").click();
    });
    expect(screen.getByText("Bye, world")).toBeInTheDocument();

    // Toast.tsx sets a 3500ms timeout to remove the message from state.
    act(() => {
      vi.advanceTimersByTime(3500);
    });

    expect(screen.queryByText("Bye, world")).not.toBeInTheDocument();
  });

  test("renders an error-styled banner when ok=false", () => {
    render(
      <ToastProvider>
        <Trigger text="Boom" ok={false} />
      </ToastProvider>,
    );

    act(() => {
      screen.getByTestId("trigger").click();
    });

    const banner = screen.getByText("Boom");
    // We don't pin the exact class string (that'd be brittle), but the
    // component branches on `ok` to set danger vs. success classes. As a
    // light contract: the banner element exists and is reachable.
    expect(banner).toBeInTheDocument();
    expect(banner.className).toMatch(/danger/);
  });

  test("multiple toasts can stack", () => {
    render(
      <ToastProvider>
        <Trigger text="first" />
      </ToastProvider>,
    );
    const btn = screen.getByTestId("trigger");

    act(() => {
      btn.click();
      btn.click();
      btn.click();
    });

    // Three banners with the same text — getAllByText returns them all.
    expect(screen.getAllByText("first")).toHaveLength(3);
  });
});
