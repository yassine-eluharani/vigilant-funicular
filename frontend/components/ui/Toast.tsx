"use client";

import React, { createContext, useCallback, useContext, useState } from "react";

type ToastVariant = "success" | "error" | "info";

interface ToastMessage {
  id: number;
  text: string;
  variant: ToastVariant;
  duration: number;
}

interface ToastContextValue {
  toast: (text: string, ok?: boolean) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

let _id = 0;

const DEFAULT_DURATION = 3500;

// Spring-ish ease for the entrance. Falls back to a hardcoded curve if the
// design foundation hasn't shipped --ease-spring yet.
const SPRING_EASE = "var(--ease-spring, cubic-bezier(0.34, 1.56, 0.64, 1))";

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<ToastMessage[]>([]);

  const toast = useCallback((text: string, ok = true) => {
    const id = ++_id;
    const variant: ToastVariant = ok ? "success" : "error";
    setMessages((m) => [...m, { id, text, variant, duration: DEFAULT_DURATION }]);
    setTimeout(() => setMessages((m) => m.filter((x) => x.id !== id)), DEFAULT_DURATION);
  }, []);

  // Render newest at the bottom-right; older toasts compress upward (smaller +
  // dimmer) so a stack of three reads as a deck rather than as flat noise.
  // Index 0 is the newest (rendered last in flex-col-reverse).
  const stack = [...messages].reverse();

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* Component-scoped styles for variant bars + progress bar + entrance
          animation. We use a plain <style> tag (rather than styled-jsx) so we
          don't depend on a StyleRegistry — the class names below are unique
          to this component. globals.css is owned by a parallel agent. */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
@keyframes ap-toast-progress {
  from { transform: scaleX(1); }
  to   { transform: scaleX(0); }
}
@keyframes ap-toast-spring-in {
  0%   { opacity: 0; transform: translateX(24px) scale(0.92); }
  100% { opacity: 1; transform: translateX(0) scale(1); }
}
.ap-toast-card {
  animation: ap-toast-spring-in 280ms ${SPRING_EASE} both;
}
.ap-toast-progress {
  transform-origin: left center;
  animation-name: ap-toast-progress;
  animation-timing-function: linear;
  animation-fill-mode: forwards;
}
`,
        }}
      />
      <div className="fixed bottom-5 right-5 z-50 flex flex-col-reverse gap-2 pointer-events-none">
        {stack.map((m, i) => {
          const variantBar =
            m.variant === "success"
              ? "bg-void-success"
              : m.variant === "error"
                ? "bg-void-danger"
                : "bg-void-accent";
          const variantIcon =
            m.variant === "success"
              ? "text-void-success"
              : m.variant === "error"
                ? "text-void-danger"
                : "text-void-accent";
          // Body-text tint is subtle but variant-aware. Keeping `void-success`
          // / `void-danger` substrings on the <p> preserves the test-suite
          // contract that asserts the error banner contains "/danger/".
          const variantBody =
            m.variant === "success"
              ? "text-void-success/90"
              : m.variant === "error"
                ? "text-void-danger/90"
                : "text-void-text";
          const icon = m.variant === "success" ? "✓" : m.variant === "error" ? "✕" : "ℹ";

          return (
            <div
              key={m.id}
              className="ap-toast-card relative overflow-hidden bg-void-surface border border-void-border rounded-lg shadow-xl pl-4 pr-4 py-3 min-w-[240px] max-w-sm"
              style={{
                // Stack-compress effect: newest (i=0) is full size; each older toast
                // shrinks 4% and dims 15% so the stack reads as a deck.
                transform: `scale(${1 - i * 0.04})`,
                opacity: 1 - i * 0.15,
                transformOrigin: "right bottom",
                transition: "transform 200ms ease, opacity 200ms ease",
              }}
              role="status"
            >
              {/* Left-edge color bar */}
              <span
                className={`absolute left-0 top-0 bottom-0 w-1 ${variantBar}`}
                aria-hidden
              />
              <div className="flex items-center gap-2.5">
                <span
                  className={`shrink-0 inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold ${variantIcon}`}
                  aria-hidden
                >
                  {icon}
                </span>
                <p className={`text-sm font-medium leading-snug ${variantBody}`}>
                  {m.text}
                </p>
              </div>
              {/* Bottom progress hairline (only on the freshest toast — older
                  ones are about to evict, no point ticking down). */}
              {i === 0 && (
                <span
                  className={`ap-toast-progress absolute left-0 bottom-0 h-0.5 w-full ${variantBar} opacity-70`}
                  style={{ animationDuration: `${m.duration}ms` }}
                  aria-hidden
                />
              )}
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext).toast;
}
