"use client";

import React, { createContext, useCallback, useContext, useState } from "react";

interface ToastMessage {
  id: number;
  text: string;
  ok: boolean;
}

interface ToastContextValue {
  toast: (text: string, ok?: boolean) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

let _id = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<ToastMessage[]>([]);

  const toast = useCallback((text: string, ok = true) => {
    const id = ++_id;
    setMessages((m) => [...m, { id, text, ok }]);
    setTimeout(() => setMessages((m) => m.filter((x) => x.id !== id)), 3500);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`
              px-4 py-3 rounded-lg text-sm font-medium shadow-xl border animate-fade-in
              ${m.ok
                ? "bg-void-surface border-void-success/40 text-void-success"
                : "bg-void-surface border-void-danger/40 text-void-danger"
              }
            `}
          >
            {m.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext).toast;
}
