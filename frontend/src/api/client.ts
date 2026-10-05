/**
 * HTTP transport shared by every endpoint module.
 *
 * Owns base-URL joining, the APP_SECURITY_KEY header, JSON decoding, and the
 * translation of transport failures into a single ApiError shape so callers
 * never inspect raw Responses.
 */

import { config } from '../config';

export class ApiError extends Error {
  readonly status: number;
  /** True when the failure is a connectivity problem rather than an HTTP status. */
  readonly isNetworkError: boolean;

  constructor(message: string, status: number, isNetworkError = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.isNetworkError = isNetworkError;
  }

  /** 401 means the key is missing or wrong; the UI can prompt for it. */
  get isAuthError(): boolean {
    return this.status === 401;
  }
}

function buildUrl(path: string, query?: Record<string, string | number | undefined>): string {
  const url = `${config.baseUrl}${path}`;
  if (!query) return url;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

function authHeaders(): Record<string, string> {
  const key = config.securityKey;
  return key ? { APP_SECURITY_KEY: key } : {};
}

/**
 * Pulls a human-readable message out of a FastAPI error body.
 *
 * Handles the shapes this backend produces: `{"detail": "..."}` from
 * HTTPException, the list-of-objects form from a 422 validation failure, and
 * the generic `{"detail": "Internal server error."}` fallback.
 */
function extractDetail(body: unknown): string | null {
  if (typeof body !== 'object' || body === null) return null;

  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item !== 'object' || item === null) return null;
        const entry = item as { msg?: unknown; loc?: unknown };
        if (typeof entry.msg !== 'string') return null;
        const field = Array.isArray(entry.loc)
          ? entry.loc.filter((p) => typeof p === 'string' || typeof p === 'number').join('.')
          : '';
        return field ? `${field}: ${entry.msg}` : entry.msg;
      })
      .filter((v): v is string => Boolean(v));

    if (messages.length > 0) return messages.join('; ');
  }

  return null;
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail: string | null = null;
  try {
    detail = extractDetail(await response.json());
  } catch {
    // Non-JSON error body; fall through to the status-based message.
  }

  if (response.status === 401) {
    return new ApiError(
      detail ?? 'The API key was rejected. Check the security key and try again.',
      401,
    );
  }
  if (response.status === 404) {
    return new ApiError(detail ?? 'The requested resource was not found.', 404);
  }
  if (response.status >= 500) {
    return new ApiError(detail ?? 'The server could not complete the request.', response.status);
  }
  return new ApiError(detail ?? `Request failed with status ${response.status}.`, response.status);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  query?: Record<string, string | number | undefined>,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      ...init,
      headers: {
        Accept: 'application/json',
        ...authHeaders(),
        ...init.headers,
      },
    });
  } catch (cause) {
    // fetch only rejects on network-level failure, which in practice means
    // the backend is not running or the origin is not reachable.
    throw new ApiError(
      'Could not reach the Memora API. Check that the backend is running.',
      0,
      true,
    );
  }

  if (!response.ok) throw await toApiError(response);

  if (response.status === 204) return undefined as T;

  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw new ApiError('The server returned a malformed response.', response.status);
  }
}

export const http = {
  get<T>(path: string, query?: Record<string, string | number | undefined>): Promise<T> {
    return request<T>(path, { method: 'GET' }, query);
  },

  post<T>(path: string, body: unknown): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  },

  delete<T>(path: string): Promise<T> {
    return request<T>(path, { method: 'DELETE' });
  },

  /**
   * Multipart upload.
   *
   * Content-Type is intentionally omitted so the browser sets the multipart
   * boundary; setting it manually produces a body the server cannot parse.
   */
  upload<T>(path: string, file: File): Promise<T> {
    const form = new FormData();
    form.append('file', file);
    return request<T>(path, { method: 'POST', body: form });
  },
};

/** Headers for the SSE request, which cannot go through `request()`. */
export function streamHeaders(): Record<string, string> {
  return { Accept: 'text/event-stream', ...authHeaders() };
}

export { buildUrl };
