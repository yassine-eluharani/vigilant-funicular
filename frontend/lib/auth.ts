/**
 * Token getter registry.
 * AuthContext registers Clerk's getToken() here on mount so that lib/api.ts
 * can attach Authorization headers without depending on React context directly.
 */

type TokenFn = () => Promise<string | null>;

let _tokenFn: TokenFn = async () => null;

export function setTokenFn(fn: TokenFn): void {
  _tokenFn = fn;
}

export async function getToken(): Promise<string | null> {
  return _tokenFn();
}

// No-op kept for call sites that still reference it (middleware cookie is gone)
export function clearToken(): void {}
