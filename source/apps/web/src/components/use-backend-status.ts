"use client";

import { useCallback, useEffect, useState } from "react";

import type { CheckStatus } from "@shopping-assistant/api-client";

import { api } from "@/lib/api";

export type BackendStatus =
  | { kind: "checking" }
  | { kind: "api-down" }
  | { kind: "db-down" }
  | { kind: "ok"; checks: CheckStatus | null };

const POLL_MS = 15_000;

/** Polls the API's health (and the price-check schedule while it's up). */
export function useBackendStatus(): { status: BackendStatus; refresh: () => void } {
  const [status, setStatus] = useState<BackendStatus>({ kind: "checking" });

  const refresh = useCallback(async () => {
    try {
      const health = await api.GET("/api/v1/health");
      if (!health.data) return setStatus({ kind: "api-down" });
      if (health.data.database !== "ok") return setStatus({ kind: "db-down" });
      const checks = await api.GET("/api/v1/checks/status");
      setStatus({ kind: "ok", checks: checks.data ?? null });
    } catch {
      setStatus({ kind: "api-down" }); // network error: the API isn't running
    }
  }, []);

  useEffect(() => {
    // Poll in the background; the first poll runs right away.
    const first = setTimeout(refresh, 0);
    const timer = setInterval(refresh, POLL_MS);
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [refresh]);

  return { status, refresh: () => void refresh() };
}
