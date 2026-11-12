import { createAuthClient } from "@neon/auth";

/**
 * Neon Auth is intentionally separate from the existing owner session.
 * Do not replace the FastAPI owner login until server-side token verification
 * and per-user authorization are implemented and tested.
 */
const baseUrl = import.meta.env.VITE_NEON_AUTH_URL;
export const neonAuthClient = baseUrl ? createAuthClient(baseUrl) : null;

export function neonAuthConfigured(): boolean {
  return Boolean(neonAuthClient);
}
