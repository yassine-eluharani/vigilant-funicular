"use client";

import { createContext, useContext, useEffect } from "react";
import {
  useUser,
  useClerk,
  useSignIn,
  useSignUp,
  useAuth as useClerkAuth,
} from "@clerk/nextjs";
import { setTokenFn } from "@/lib/auth";

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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn, user } = useUser();
  const { signOut } = useClerk();
  const { isLoaded: siLoaded, signIn, setActive: siSetActive } = useSignIn();
  const { isLoaded: suLoaded, signUp, setActive: suSetActive } = useSignUp();
  const { getToken } = useClerkAuth();

  // Wire Clerk's token getter into lib/api.ts so all API calls get Authorization headers
  useEffect(() => {
    setTokenFn(() => getToken());
  }, [getToken]);

  const login = async (email: string, password: string) => {
    if (!siLoaded || !signIn) return { ok: false, error: "Auth not ready" };
    try {
      const result = await signIn.create({ identifier: email, password });
      if (result.status === "complete") {
        await siSetActive!({ session: result.createdSessionId });
        return { ok: true };
      }
      return { ok: false, error: "Additional verification required" };
    } catch (e: unknown) {
      const err = e as { errors?: Array<{ message: string }> };
      return { ok: false, error: err.errors?.[0]?.message ?? "Incorrect email or password" };
    }
  };

  const register = async (fullName: string, email: string, password: string) => {
    if (!suLoaded || !signUp) return { ok: false, error: "Auth not ready" };
    try {
      const [firstName, ...rest] = fullName.trim().split(/\s+/);
      const result = await signUp.create({
        firstName,
        lastName: rest.join(" ") || undefined,
        emailAddress: email,
        password,
      });
      if (result.status === "complete") {
        await suSetActive!({ session: result.createdSessionId });
        return { ok: true };
      }
      // Email verification required — prepare the verification email
      await result.prepareEmailAddressVerification({ strategy: "email_code" });
      return { ok: false, error: "Check your email for a verification code, then sign in." };
    } catch (e: unknown) {
      const err = e as { errors?: Array<{ message: string }> };
      return { ok: false, error: err.errors?.[0]?.message ?? "Registration failed" };
    }
  };

  const logout = () => signOut({ redirectUrl: "/" });

  const userObj: User | null =
    isSignedIn && user
      ? {
          id: user.id,
          email: user.primaryEmailAddress?.emailAddress ?? "",
          full_name: user.fullName ?? "",
        }
      : null;

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: !!isSignedIn,
        isLoading: !isLoaded,
        user: userObj,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
