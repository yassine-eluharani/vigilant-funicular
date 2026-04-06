"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { getToken, setToken, clearToken, isTokenValid } from "@/lib/auth";

interface User {
  id: string;
  email: string;
  full_name: string;
}

interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: User | null;
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  register: (fullName: string, email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  isLoading: true,
  user: null,
  login: async () => ({ ok: false }),
  register: async () => ({ ok: false }),
  logout: () => {},
});

const BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : (process.env.API_URL ?? "http://backend:8000");

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);

  // On mount: validate stored token
  useEffect(() => {
    const token = getToken();
    if (!isTokenValid(token)) {
      clearToken();
      setIsLoading(false);
      return;
    }
    fetch(`${BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (r) => {
        if (r.ok) {
          const data = await r.json();
          setUser({ id: data.id, email: data.email, full_name: data.full_name });
          setIsAuthenticated(true);
        } else {
          clearToken();
        }
      })
      .catch(() => {
        // Network issue — trust token expiry check
        if (isTokenValid(token)) setIsAuthenticated(true);
        else clearToken();
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    try {
      const res = await fetch(`${BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        return { ok: false, error: body.detail ?? "Incorrect email or password" };
      }
      const { access_token, user: u } = await res.json();
      setToken(access_token);
      setUser(u);
      setIsAuthenticated(true);
      return { ok: true };
    } catch {
      return { ok: false, error: "Could not reach the server" };
    }
  }, []);

  const register = useCallback(async (fullName: string, email: string, password: string) => {
    try {
      const res = await fetch(`${BASE}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: fullName, email, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        return { ok: false, error: body.detail ?? "Registration failed" };
      }
      const { access_token, user: u } = await res.json();
      setToken(access_token);
      setUser(u);
      setIsAuthenticated(true);
      return { ok: true };
    } catch {
      return { ok: false, error: "Could not reach the server" };
    }
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setIsAuthenticated(false);
    setUser(null);
    router.push("/");
  }, [router]);

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
