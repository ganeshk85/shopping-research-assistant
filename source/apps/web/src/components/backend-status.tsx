"use client";

import type { CheckStatus } from "@shopping-assistant/api-client";

import { API_BASE_URL } from "@/lib/api";
import { fromNow } from "@/lib/format";

import { useBackendStatus } from "./use-backend-status";

/** "API unreachable" / "database unavailable" banner, else a one-line price-check schedule. */
export function BackendStatus() {
  const { status, refresh } = useBackendStatus();

  if (status.kind === "api-down") {
    return (
      <Banner title="Can't reach the assistant's API" onRetry={refresh}>
        Nothing can load until it&apos;s running at <Code>{API_BASE_URL}</Code>. Start it in a terminal from the{" "}
        <Code>source</Code> folder:
        <Command>.venv\Scripts\shopping-assistant api serve</Command>
      </Banner>
    );
  }
  if (status.kind === "db-down") {
    return (
      <Banner title="The API is running, but its database isn't available" onRetry={refresh}>
        Check that the PostgreSQL service is running and that <Code>DATABASE_URL</Code> in <Code>source/.env</Code>{" "}
        is right, then run <Code>shopping-assistant db migrate</Code>.
      </Banner>
    );
  }
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pt-3 sm:px-6">
      <p className="text-xs text-stone-500 dark:text-stone-400" aria-live="polite">
        {status.kind === "checking" ? "Connecting to the assistant…" : <Schedule checks={status.checks} />}
      </p>
    </div>
  );
}

function Schedule({ checks }: { checks: CheckStatus | null }) {
  if (!checks) return null;
  const parts: string[] = [];
  if (checks.running) parts.push("Checking prices now…");
  else if (checks.last_finished?.finished_at) parts.push(`Last price check ${fromNow(checks.last_finished.finished_at)}`);
  else parts.push("No price checks yet");

  const { schedule } = checks;
  if (schedule.worker_running && schedule.next_run_at) parts.push(`next ${fromNow(schedule.next_run_at)}`);
  return (
    <>
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className={`size-1.5 rounded-full ${schedule.worker_running ? "bg-emerald-500" : "bg-stone-400"}`}
        />
        {parts.join(" · ")}
      </span>
      {!schedule.worker_running && (
        <span>
          {" "}
          · Background checks are off. Start them with <Code>shopping-assistant worker</Code>.
        </span>
      )}
    </>
  );
}

function Banner({ title, children, onRetry }: { title: string; children: React.ReactNode; onRetry: () => void }) {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pt-4 sm:px-6">
      <div
        role="alert"
        className="flex flex-col gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 sm:flex-row sm:items-start sm:justify-between dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-100"
      >
        <div className="min-w-0 space-y-1">
          <p className="font-semibold">{title}</p>
          <div className="leading-relaxed text-amber-900 dark:text-amber-200">{children}</div>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 self-start rounded-lg border border-amber-400 px-3 py-1.5 font-medium hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 dark:border-amber-600 dark:hover:bg-amber-900/50"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-black/5 px-1 py-0.5 font-mono text-[0.85em] [overflow-wrap:anywhere] dark:bg-white/10">
      {children}
    </code>
  );
}

/** A command on its own line; scrolls sideways on narrow screens instead of breaking. */
function Command({ children }: { children: React.ReactNode }) {
  return (
    <pre className="mt-2 overflow-x-auto rounded-lg bg-black/5 px-3 py-2 font-mono text-[0.85em] dark:bg-white/10">
      <code>{children}</code>
    </pre>
  );
}
