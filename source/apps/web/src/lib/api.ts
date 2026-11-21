import {
  ApiError,
  createApiClient,
  DEFAULT_BASE_URL,
  streamMessage,
  type CheckRun,
  type CheckStatus,
  type ConfirmTracking,
  type ErrorBody,
  type NotificationSettings,
  type PriceHistory,
  type StreamEvent,
  type TestAlertResult,
  type ThreadDetail,
  type ThreadSummary,
  type TurnResult,
  type UpdateNotificationSettings,
  type UpdateWatchlistItem,
  type WatchlistItem,
} from "@shopping-assistant/api-client";

/**
 * Where the API runs. The one web setting (US-36): set NEXT_PUBLIC_API_BASE_URL in
 * apps/web/.env.local to change it; it is read at build time.
 */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, "");

/** The shared typed client. Paths are full API paths, e.g. `api.GET("/api/v1/health")`. */
export const api = createApiClient(API_BASE_URL);

export { ApiError };

type Result<T> = { data?: T; error?: unknown; response: Response };

/** The data, or an ApiError carrying the server's {code, message}. Network failures become `network_error`. */
async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await call;
  } catch (cause) {
    throw new ApiError(0, { code: "network_error", message: "Can't reach the API. Is it running?", details: String(cause) });
  }
  if (result.error !== undefined || !result.response.ok) {
    const body = result.error as Partial<ErrorBody> | undefined;
    throw new ApiError(result.response.status, {
      code: body?.code ?? "http_error",
      message: body?.message ?? (result.response.statusText || "Request failed."),
      details: body?.details ?? null,
    });
  }
  return result.data as T;
}

/** A plain-language message for any error, for showing to the user. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.body.message;
  return "Something went wrong. Please try again.";
}

// --- research (the calls the research page makes; mocked in component tests) ---------------

export const research = {
  listThreads: (): Promise<ThreadSummary[]> => unwrap(api.GET("/api/v1/threads", { params: { query: { limit: 50 } } })),

  newThread: async (): Promise<string> => (await unwrap(api.POST("/api/v1/threads"))).thread_id,

  getThread: (threadId: string): Promise<ThreadDetail> =>
    unwrap(api.GET("/api/v1/threads/{thread_id}", { params: { path: { thread_id: threadId } } })),

  confirm: (threadId: string, body: ConfirmTracking): Promise<TurnResult> =>
    unwrap(api.POST("/api/v1/threads/{thread_id}/confirmation", { params: { path: { thread_id: threadId } }, body })),

  /** `progress` events, then one `result` or `error`. Throws ApiError if refused before streaming. */
  send: (threadId: string, text: string, signal?: AbortSignal): AsyncGenerator<StreamEvent> =>
    streamMessage(threadId, text, { baseUrl: API_BASE_URL, signal }),
};

// --- watchlist and price checks (US-39, US-40) -------------------------------------------------

const item = (id: number) => ({ params: { path: { item_id: id } } });

export const watchlist = {
  list: (): Promise<WatchlistItem[]> => unwrap(api.GET("/api/v1/watchlist")),

  update: (id: number, body: UpdateWatchlistItem): Promise<WatchlistItem> =>
    unwrap(api.PATCH("/api/v1/watchlist/{item_id}", { ...item(id), body })),

  remove: async (id: number): Promise<void> => {
    await unwrap(api.DELETE("/api/v1/watchlist/{item_id}", item(id)));
  },

  history: (id: number): Promise<PriceHistory> => unwrap(api.GET("/api/v1/watchlist/{item_id}/history", item(id))),
};

export const checks = {
  start: (): Promise<CheckRun> => unwrap(api.POST("/api/v1/checks")),

  get: (id: number): Promise<CheckRun> =>
    unwrap(api.GET("/api/v1/checks/{check_id}", { params: { path: { check_id: id } } })),

  status: (): Promise<CheckStatus> => unwrap(api.GET("/api/v1/checks/status")),
};

// --- notification settings (US-41) ------------------------------------------------------------

export const notificationSettings = {
  get: (): Promise<NotificationSettings> => unwrap(api.GET("/api/v1/settings/notifications")),

  save: (body: UpdateNotificationSettings): Promise<NotificationSettings> =>
    unwrap(api.PUT("/api/v1/settings/notifications", { body })),

  reset: async (): Promise<void> => {
    await unwrap(api.DELETE("/api/v1/settings/notifications"));
  },

  test: (): Promise<TestAlertResult> => unwrap(api.POST("/api/v1/settings/notifications/test")),
};
