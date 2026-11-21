"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { CheckRun } from "@shopping-assistant/api-client";

import { checks, errorMessage } from "@/lib/api";
import { fromNow } from "@/lib/format";

/** One line describing how a check ended. */
export function describeRun(run: CheckRun): string {
  if (run.status === "failed") return `The price check failed: ${run.error ?? "unknown error"}.`;
  if (!run.active_items) return "No active items to check.";
  let text =
    `Checked ${run.checked ?? 0} of ${run.active_items} item(s): ${run.alerts_sent ?? 0} alert(s) sent` +
    (run.failed ? `, ${run.failed} check(s) failed` : "") +
    ".";
  if (run.alerts_failed) text += ` ${run.alerts_failed} alert(s) couldn't be delivered and will be retried.`;
  return text;
}

/**
 * "Check now" (US-39 via US-32): starts a check, polls it, then reports the summary.
 * Disabled while any check runs, including one started by the worker or the CLI.
 */
export function CheckNow({ onFinished, pollMs = 2000 }: { onFinished: () => void; pollMs?: number }) {
  const [running, setRunning] = useState<CheckRun | null>(null);
  const [last, setLast] = useState<CheckRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const follow = useCallback(
    (run: CheckRun) => {
      setRunning(run);
      const poll = async () => {
        try {
          const now = await checks.get(run.id);
          if (now.status === "running") {
            timer.current = setTimeout(poll, pollMs);
            return;
          }
          setRunning(null);
          setLast(now);
          onFinished();
        } catch (e) {
          setRunning(null);
          setError(errorMessage(e));
        }
      };
      timer.current = setTimeout(poll, pollMs);
    },
    [onFinished, pollMs],
  );

  // Pick up a check already in progress (e.g. the worker's) and the last result.
  useEffect(() => {
    let cancelled = false;
    checks
      .status()
      .then((s) => {
        if (cancelled) return;
        setLast(s.last_finished ?? null);
        if (s.running) follow(s.running);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [follow]);

  async function start() {
    setError(null);
    setStarting(true);
    try {
      follow(await checks.start());
    } catch (e) {
      // Refused because another check is running? Follow that one instead.
      const status = await checks.status().catch(() => null);
      if (status?.running) follow(status.running);
      else setError(errorMessage(e));
    } finally {
      setStarting(false);
    }
  }

  const busy = Boolean(running) || starting;
  return (
    <div className="space-y-1 sm:text-right">
      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="inline-flex items-center gap-2 rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700 disabled:opacity-60 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
      >
        {busy && (
          <span aria-hidden className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
        )}
        {busy ? "Checking prices…" : "Check now"}
      </button>
      <p aria-live="polite" className="text-xs text-stone-500 dark:text-stone-400">
        {running
          ? `Started ${fromNow(running.started_at)}${running.trigger === "api" ? "" : ` by the ${running.trigger === "schedule" ? "background worker" : "CLI"}`}; each retailer page is checked, so this can take a minute.`
          : last
            ? `${describeRun(last)} (${fromNow(last.finished_at ?? last.started_at)})`
            : "Checks every active item's price now."}
      </p>
      {error && (
        <p role="alert" className="text-xs font-medium text-rose-700 dark:text-rose-400">
          {error}
        </p>
      )}
    </div>
  );
}
