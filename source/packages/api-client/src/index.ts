/**
 * Typed client for the Shopping Research Assistant API (/api/v1).
 *
 * - `createApiClient()` covers every JSON endpoint, fully typed from `schema.ts`
 *   (generated from ../openapi.json: `npm run generate`).
 * - `streamMessage()` sends a chat message and yields the Server-Sent Events
 *   (`progress`..., then one `result` or `error`).
 *
 * Shared by the web app and, later, the mobile app. The API never takes a user ID:
 * the server decides who the user is.
 */
import createFetchClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type { components, paths };

type Schemas = components["schemas"];
export type ErrorBody = Schemas["ErrorBody"];
export type Health = Schemas["Health"];
export type ThreadSummary = Schemas["ThreadSummary"];
export type ThreadDetail = Schemas["ThreadDetail"];
export type ChatMessage = Schemas["ChatMessage"];
export type ResearchComparison = Schemas["ResearchComparison"];
export type ProductCandidate = Schemas["ProductCandidate"];
export type FinalizedProduct = Schemas["FinalizedProduct"];
export type RetailListing = Schemas["RetailListing"];
export type PendingConfirmation = Schemas["PendingConfirmation"];
export type ConfirmTracking = Schemas["ConfirmTracking"];
export type TurnResult = Schemas["TurnResult"];
export type ProgressEvent = Schemas["ProgressEvent"];
export type StreamEvent = Schemas["StreamEvent"];
export type WatchlistItem = Schemas["WatchlistItem"];
export type UpdateWatchlistItem = Schemas["UpdateWatchlistItem"];
export type PriceHistory = Schemas["PriceHistory"];
export type PriceHistoryEntry = Schemas["PriceHistoryEntryOut"];
export type CheckRun = Schemas["CheckRun"];
export type CheckStatus = Schemas["CheckStatus"];
export type ScheduleStatus = Schemas["ScheduleStatus"];
export type NotificationSettings = Schemas["NotificationSettingsOut"];
export type UpdateNotificationSettings = Schemas["UpdateNotificationSettings"];
export type TestAlertResult = Schemas["TestAlertResult"];

export const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

/** Typed fetch client; paths are relative to the server root, e.g. `client.GET("/api/v1/watchlist")`. */
export function createApiClient(baseUrl: string = DEFAULT_BASE_URL) {
  return createFetchClient<paths>({ baseUrl });
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** An error response from the API (or a network failure, with code "network_error"). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ErrorBody,
  ) {
    super(body.message);
    this.name = "ApiError";
  }
}

async function errorFrom(response: Response): Promise<ApiError> {
  try {
    return new ApiError(response.status, (await response.json()) as ErrorBody);
  } catch {
    return new ApiError(response.status, {
      code: "http_error",
      message: response.statusText || "Request failed.",
      details: null,
    });
  }
}

/** Split an SSE text buffer into complete events; returns the events and the unparsed remainder. */
export function parseSseChunk(buffer: string): { events: StreamEvent[]; rest: string } {
  const events: StreamEvent[] = [];
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    let event = "";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (event && data.length) events.push({ event, data: JSON.parse(data.join("\n")) } as StreamEvent);
  }
  return { events, rest };
}

/**
 * Send a message and yield its events as they arrive. Throws `ApiError` if the request is
 * rejected before streaming starts (404 unknown thread, 409 busy, 422 empty text, 503 not set up).
 */
export async function* streamMessage(
  threadId: string,
  text: string,
  options: { baseUrl?: string; signal?: AbortSignal } = {},
): AsyncGenerator<StreamEvent> {
  const url = `${options.baseUrl ?? DEFAULT_BASE_URL}/api/v1/threads/${encodeURIComponent(threadId)}/messages`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ text }),
      signal: options.signal,
    });
  } catch (cause) {
    throw new ApiError(0, { code: "network_error", message: "Can't reach the API. Is it running?", details: String(cause) });
  }
  if (!response.ok || !response.body) throw await errorFrom(response);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseSseChunk(buffer + value);
    buffer = parsed.rest;
    yield* parsed.events;
  }
}
