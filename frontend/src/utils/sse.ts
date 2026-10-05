/**
 * SSE parsing for POST /chat/stream.
 *
 * EventSource cannot be used here: the endpoint is POST-only and requires an
 * APP_SECURITY_KEY header, neither of which EventSource supports. The body is
 * therefore read from a fetch() ReadableStream and decoded here.
 *
 * The parser follows the SSE framing rules that matter for this backend:
 * frames separated by a blank line, `data:` lines joined with newlines, and
 * comments (`:` prefixed) ignored.
 */

import { ApiError, buildUrl, streamHeaders } from '../api/client';
import type { ChatRequestDto, RetrievalSource, StreamEvent } from '../types/api';

/** The backend's terminal sentinel, sent as a bare `data: [DONE]`. */
const DONE_SENTINEL = '[DONE]';

function isDoneSentinel(data: string): boolean {
  return data.trim() === DONE_SENTINEL;
}

/**
 * Narrows a decoded payload to a known StreamEvent.
 *
 * The backend is trusted to send well-formed JSON, but an unrecognised or
 * partially-typed event is skipped rather than thrown on, so an added event
 * type degrades to "ignored" instead of breaking the stream.
 */
function parseEvent(data: string): StreamEvent | null {
  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch {
    return null;
  }

  if (typeof payload !== 'object' || payload === null) return null;

  const event = payload as { type?: unknown } & Record<string, unknown>;
  switch (event.type) {
    case 'chunk':
      return typeof event.content === 'string'
        ? { type: 'chunk', content: event.content }
        : null;

    case 'tool_start':
      return {
        type: 'tool_start',
        name: typeof event.name === 'string' ? event.name : 'tool',
        status: typeof event.status === 'string' ? event.status : '',
      };

    case 'tool_end':
      return { type: 'tool_end', name: typeof event.name === 'string' ? event.name : 'tool' };

    case 'done':
      return {
        type: 'done',
        session_id: typeof event.session_id === 'string' ? event.session_id : '',
      };

    case 'error':
      return {
        type: 'error',
        message: typeof event.message === 'string' ? event.message : 'The stream failed.',
      };

    case 'sources': {
      // Not emitted by the current backend, but handled so retrieval data is
      // rendered the moment it is sent. Entries without a usable label are
      // dropped rather than shown as blank rows.
      const raw = event.sources;
      if (!Array.isArray(raw)) return null;

      const sources = raw
        .map((entry): RetrievalSource | null => {
          if (typeof entry !== 'object' || entry === null) return null;
          const item = entry as Record<string, unknown>;
          const label =
            typeof item.label === 'string'
              ? item.label
              : typeof item.filename === 'string'
                ? item.filename
                : '';
          if (!label) return null;

          return {
            label,
            ...(typeof item.filename === 'string' ? { filename: item.filename } : {}),
            ...(typeof item.chunk === 'number' || typeof item.chunk === 'string'
              ? { chunk: item.chunk }
              : {}),
            ...(typeof item.url === 'string' ? { url: item.url } : {}),
            ...(typeof item.score === 'number' ? { score: item.score } : {}),
            ...(typeof item.snippet === 'string' ? { snippet: item.snippet } : {}),
            ...(typeof item.metadata === 'object' && item.metadata !== null
              ? { metadata: item.metadata as Record<string, unknown> }
              : {}),
          };
        })
        .filter((s): s is RetrievalSource => s !== null);

      return sources.length > 0 ? { type: 'sources', sources } : null;
    }

    default:
      return null;
  }
}

/**
 * Splits a buffer into complete SSE frames plus the unconsumed remainder.
 *
 * Chunk boundaries do not align with frame boundaries, so the tail is carried
 * over to the next read.
 */
function extractFrames(buffer: string): { frames: string[]; rest: string } {
  // Normalise CRLF so a single split handles both line endings.
  const normalised = buffer.replace(/\r\n/g, '\n');
  const parts = normalised.split('\n\n');
  const rest = parts.pop() ?? '';
  return { frames: parts, rest };
}

/** Collapses the `data:` lines of one frame into the event payload. */
function frameData(frame: string): string | null {
  const lines: string[] = [];

  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue; // comment / keep-alive
    if (!line.startsWith('data:')) continue;
    // A single leading space after the colon is part of the framing.
    lines.push(line.slice(5).replace(/^ /, ''));
  }

  if (lines.length === 0) return null;
  return lines.join('\n');
}

export interface StreamChatOptions {
  request: ChatRequestDto;
  signal: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}

/**
 * Opens the chat stream and dispatches parsed events until completion.
 *
 * Throws ApiError on transport failure. An `error` event from the backend is
 * delivered through onEvent rather than thrown, because the response has
 * already begun by that point and the partial text is still worth showing.
 */
export async function streamChat({ request, signal, onEvent }: StreamChatOptions): Promise<void> {
  let response: Response;

  try {
    response = await fetch(buildUrl('/chat/stream'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...streamHeaders(),
      },
      body: JSON.stringify(request),
      signal,
    });
  } catch (cause) {
    if (signal.aborted) throw cause;
    throw new ApiError(
      'Could not reach the Memora API. Check that the backend is running.',
      0,
      true,
    );
  }

  if (!response.ok) {
    let detail: string | null = null;
    try {
      const body: unknown = await response.json();
      if (typeof body === 'object' && body !== null) {
        const raw = (body as { detail?: unknown }).detail;
        if (typeof raw === 'string') detail = raw;
      }
    } catch {
      // Fall through to the status message.
    }
    throw new ApiError(detail ?? `The stream request failed (${response.status}).`, response.status);
  }

  if (!response.body) {
    throw new ApiError('The server returned an empty stream.', response.status);
  }

  const reader = response.body.getReader();
  // stream: true keeps multi-byte characters intact across chunk boundaries.
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const { frames, rest } = extractFrames(buffer);
      buffer = rest;

      for (const frame of frames) {
        const data = frameData(frame);
        if (data === null || isDoneSentinel(data)) continue;

        const event = parseEvent(data);
        if (event) onEvent(event);
      }
    }

    // Flush any frame that arrived without its terminating blank line.
    buffer += decoder.decode();
    const trailing = frameData(buffer);
    if (trailing && !isDoneSentinel(trailing)) {
      const event = parseEvent(trailing);
      if (event) onEvent(event);
    }
  } finally {
    // Releasing the lock lets an aborted fetch tear the connection down.
    reader.releaseLock();
  }
}
