/**
 * Runtime configuration.
 *
 * All environment access is funnelled through this module so the rest of the
 * app never touches import.meta.env directly, and so the auth strategy can be
 * replaced without touching the API layer's call sites.
 */

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.trim() || 'http://localhost:8000/api/v1';

/**
 * Value for the APP_SECURITY_KEY header.
 *
 * backend/app/core/security.py reads the key from an `APP_SECURITY_KEY`
 * request header, not an Authorization bearer token.
 *
 * Resolution order: a runtime override (so a key can be supplied without a
 * rebuild), then the build-time env var. Anything in a browser bundle is
 * readable by the user, so this is a local/demo convenience, not a secret.
 */
const RUNTIME_KEY_STORAGE = 'memora.securityKey';

function readStoredKey(): string | null {
  try {
    return window.localStorage.getItem(RUNTIME_KEY_STORAGE);
  } catch {
    // Private browsing modes can throw on localStorage access.
    return null;
  }
}

let overrideKey: string | null = readStoredKey();

export const config = {
  baseUrl: BASE_URL.replace(/\/+$/, ''),
  get securityKey(): string {
    return (overrideKey ?? import.meta.env.VITE_APP_SECURITY_KEY ?? '').trim();
  },
  hasSecurityKey(): boolean {
    return this.securityKey.length > 0;
  },
  setSecurityKey(value: string): void {
    overrideKey = value.trim() || null;
    try {
      if (overrideKey === null) {
        window.localStorage.removeItem(RUNTIME_KEY_STORAGE);
      } else {
        window.localStorage.setItem(RUNTIME_KEY_STORAGE, overrideKey);
      }
    } catch {
      // A key that cannot be persisted still works for this tab.
    }
  },
};

/** Mirrors settings.ALLOWED_EXTENSIONS so the client can reject early. */
export const ALLOWED_EXTENSIONS = ['.pdf', '.txt', '.md', '.docx'] as const;

/** Mirrors settings.MAX_UPLOAD_BYTES (25 MB). */
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

export const ACCEPTED_UPLOAD_ATTRIBUTE = ALLOWED_EXTENSIONS.join(',');
