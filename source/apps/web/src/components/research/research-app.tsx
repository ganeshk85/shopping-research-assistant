"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import type {
  ChatMessage,
  ConfirmTracking,
  ProductCandidate,
  ProgressEvent,
  ThreadDetail,
  ThreadSummary,
} from "@shopping-assistant/api-client";

import { errorMessage, research } from "@/lib/api";
import { fromNow } from "@/lib/format";

import { ComparisonCards } from "./comparison-cards";
import { ListingList } from "./listings";
import { TrackingForm } from "./tracking-form";

type Turn =
  | { kind: "idle" }
  | { kind: "running"; text: string; steps: ProgressEvent[] }
  | { kind: "failed"; text: string; error: string };

type Confirming = { busy: boolean; error: string | null };

const EMPTY_PROMPTS = [
  "Noise-cancelling headphones for flights, under $400",
  "A 27-inch 4K monitor for photo editing under $600",
  "A quiet robot vacuum for a small apartment with pets",
];

/** The research chat (US-37) with tracking confirmation (US-38). Thread is kept in `?thread=`. */
export function ResearchApp() {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [turn, setTurn] = useState<Turn>({ kind: "idle" });
  const [confirming, setConfirming] = useState<Confirming>({ busy: false, error: null });
  const [saved, setSaved] = useState<number[]>([]);
  const [showThreads, setShowThreads] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await research.listThreads());
    } catch {
      /* the status banner already says when the API is down */
    }
  }, []);

  const open = useCallback(async (id: string | null) => {
    setThreadId(id);
    setDetail(null);
    setTurn({ kind: "idle" });
    setConfirming({ busy: false, error: null });
    setSaved([]);
    setLoadError(null);
    setShowThreads(false);
    window.history.replaceState(null, "", id ? `/research?thread=${encodeURIComponent(id)}` : "/research");
    if (!id) return;
    try {
      setDetail(await research.getThread(id));
    } catch (error) {
      setLoadError(errorMessage(error));
    }
  }, []);

  // Restore the thread from the URL (a reload keeps your place, including a pending confirmation).
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("thread");
    const timer = setTimeout(() => {
      void refreshThreads();
      if (id) void open(id);
    }, 0);
    return () => clearTimeout(timer);
  }, [open, refreshThreads]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [detail, turn, saved]);

  async function send(text: string) {
    if (turn.kind === "running") return;
    setSaved([]);
    setTurn({ kind: "running", text, steps: [] });
    try {
      let id = threadId;
      if (!id) {
        id = await research.newThread();
        setThreadId(id);
        window.history.replaceState(null, "", `/research?thread=${encodeURIComponent(id)}`);
      }
      let failed: string | null = null;
      for await (const event of research.send(id, text)) {
        if (event.event === "progress") {
          const step = event.data;
          setTurn((t) => (t.kind === "running" ? { ...t, steps: [...t.steps, step] } : t));
        } else if (event.event === "error") {
          failed = event.data.message;
        }
      }
      if (failed) return setTurn({ kind: "failed", text, error: failed });
      setDetail(await research.getThread(id));
      setConfirming({ busy: false, error: null });
      setTurn({ kind: "idle" });
      void refreshThreads();
    } catch (error) {
      setTurn({ kind: "failed", text, error: errorMessage(error) });
    }
  }

  async function confirm(decision: ConfirmTracking) {
    if (!threadId) return;
    setConfirming({ busy: true, error: null });
    try {
      const result = await research.confirm(threadId, decision);
      setDetail(await research.getThread(threadId));
      setConfirming({ busy: false, error: null });
      setSaved(result.saved_item_ids ?? []);
      void refreshThreads();
    } catch (error) {
      setConfirming({ busy: false, error: errorMessage(error) });
    }
  }

  const messages = detail?.messages ?? [];
  const pending = detail?.pending_confirmation ?? null;
  const latestComparisonIndex = messages.findLastIndex((m) => m.comparison);
  // While a confirmation is pending, its listings appear in the form, so don't repeat them above it.
  const pendingListingsIndex = pending ? messages.findLastIndex((m) => m.listings) : -1;
  const running = turn.kind === "running";
  const canChoose = !running && !confirming.busy;

  function choose(n: number, candidate: ProductCandidate) {
    void send(`I'll go with option ${n}: ${candidate.name}`);
  }

  return (
    <div className="grid gap-6 md:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className={`${showThreads ? "block" : "hidden"} md:block`}>
        <ThreadList threads={threads} activeId={threadId} onOpen={open} />
      </aside>

      <section aria-label="Conversation" className="min-w-0 space-y-4">
        <div className="flex items-center justify-between gap-2 md:hidden">
          <button
            type="button"
            onClick={() => setShowThreads((s) => !s)}
            aria-expanded={showThreads}
            className="rounded-lg border border-stone-300 px-3 py-1.5 text-sm font-medium dark:border-stone-700"
          >
            {showThreads ? "Hide conversations" : `Conversations (${threads.length})`}
          </button>
          <button type="button" onClick={() => open(null)} className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
            + New research
          </button>
        </div>

        {loadError && (
          <p role="alert" className="rounded-xl bg-rose-50 p-4 text-sm text-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
            {loadError}
          </p>
        )}

        {!threadId && turn.kind === "idle" && <EmptyState onPick={send} />}

        <ol className="space-y-5">
          {messages.map((m, i) => (
            <li key={i}>
              <Message
                message={i === pendingListingsIndex ? { ...m, listings: null } : m}
                listingsInForm={i === pendingListingsIndex}
                chosenName={detail?.finalized_product?.name ?? null}
                onChoose={i === latestComparisonIndex && canChoose ? choose : undefined}
              />
            </li>
          ))}
          {turn.kind !== "idle" && (
            <li>
              <UserBubble text={turn.text} />
            </li>
          )}
        </ol>

        {turn.kind === "running" && <Progress steps={turn.steps} />}
        {turn.kind === "failed" && (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl bg-rose-50 p-4 text-sm text-rose-900 dark:bg-rose-950/40 dark:text-rose-100">
            <p className="min-w-0 flex-1">
              <span className="font-semibold">That didn&apos;t work.</span> {turn.error} Your message is kept.
            </p>
            <button
              type="button"
              onClick={() => send(turn.text)}
              className="rounded-lg bg-rose-700 px-3 py-1.5 font-medium text-white hover:bg-rose-800"
            >
              Retry
            </button>
          </div>
        )}

        {pending && turn.kind === "idle" && (
          <TrackingForm
            key={`${threadId}-${messages.length}`}
            pending={pending}
            busy={confirming.busy}
            error={confirming.error}
            onSubmit={confirm}
          />
        )}

        {saved.length > 0 && (
          <p className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-950 dark:bg-emerald-950/40 dark:text-emerald-100">
            Tracking is set up for {saved.length} listing{saved.length === 1 ? "" : "s"}.{" "}
            <Link href="/watchlist" className="font-semibold underline underline-offset-2">
              Go to your watchlist
            </Link>
          </p>
        )}

        <Composer
          disabled={running || confirming.busy}
          pendingConfirmation={Boolean(pending)}
          isNew={!threadId}
          onSend={send}
        />
        {/* Below the composer, so scrolling here shows the newest message in full. */}
        <div ref={endRef} />
      </section>
    </div>
  );
}

function ThreadList({
  threads,
  activeId,
  onOpen,
}: {
  threads: ThreadSummary[];
  activeId: string | null;
  onOpen: (id: string | null) => void;
}) {
  return (
    <nav aria-label="Conversations" className="space-y-2">
      <button
        type="button"
        onClick={() => onOpen(null)}
        className="hidden w-full rounded-lg bg-stone-900 px-3 py-2 text-sm font-semibold text-white hover:bg-stone-700 md:block dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
      >
        + New research
      </button>
      {threads.length === 0 ? (
        <p className="px-1 text-sm text-stone-500 dark:text-stone-400">Your conversations will be listed here.</p>
      ) : (
        <ul className="space-y-1">
          {threads.map((t) => (
            <li key={t.thread_id}>
              <button
                type="button"
                onClick={() => onOpen(t.thread_id)}
                aria-current={t.thread_id === activeId ? "true" : undefined}
                className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-stone-100 aria-[current=true]:bg-white aria-[current=true]:shadow-sm aria-[current=true]:ring-1 aria-[current=true]:ring-stone-200 dark:hover:bg-stone-900 dark:aria-[current=true]:bg-stone-900 dark:aria-[current=true]:ring-stone-800"
              >
                <span className="line-clamp-2 font-medium">{t.title}</span>
                <span className="block text-xs text-stone-500 dark:text-stone-400">
                  {t.finalized_product ? `Chose ${t.finalized_product} · ` : ""}
                  {fromNow(t.updated_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}

function Message({
  message,
  chosenName,
  onChoose,
  listingsInForm = false,
}: {
  message: ChatMessage;
  chosenName: string | null;
  onChoose?: (n: number, candidate: ProductCandidate) => void;
  listingsInForm?: boolean;
}) {
  if (message.role === "user") return <UserBubble text={message.text} />;
  if (message.comparison) {
    return <ComparisonCards comparison={message.comparison} onChoose={onChoose} chosenName={chosenName} />;
  }
  return (
    <div className="space-y-3">
      <AssistantText text={message.listings || listingsInForm ? firstLine(message.text) : message.text} />
      {message.listings && <ListingList listings={message.listings} />}
    </div>
  );
}

function firstLine(text: string): string {
  return text.split("\n")[0];
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-stone-900 px-4 py-2 whitespace-pre-wrap text-white dark:bg-stone-100 dark:text-stone-900">
        {text}
      </p>
    </div>
  );
}

function AssistantText({ text }: { text: string }) {
  return <p className="max-w-prose leading-relaxed whitespace-pre-wrap">{text}</p>;
}

function Progress({ steps }: { steps: ProgressEvent[] }) {
  const current = steps.at(-1);
  return (
    <div role="status" aria-live="polite" className="flex items-start gap-3 text-sm text-stone-600 dark:text-stone-400">
      <span aria-hidden className="mt-1 size-3 shrink-0 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
      <div>
        <p className="font-medium text-stone-900 dark:text-stone-100">{current ? `${current.message}…` : "Working…"}</p>
        {steps.length > 1 && (
          <ul className="mt-1 space-y-0.5 text-xs">
            {steps.slice(0, -1).map((s, i) => (
              <li key={i}>✓ {s.message}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="rounded-2xl border border-dashed border-stone-300 p-6 dark:border-stone-700">
      <p className="font-medium">What are you shopping for?</p>
      <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
        Describe the need, your budget and anything that matters. You&apos;ll get 3–4 options compared from independent
        reviews, then I can track the price at Canadian retailers.
      </p>
      <ul className="mt-4 flex flex-wrap gap-2">
        {EMPTY_PROMPTS.map((p) => (
          <li key={p}>
            <button
              type="button"
              onClick={() => onPick(p)}
              className="rounded-full border border-stone-300 px-3 py-1.5 text-left text-sm hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-900"
            >
              {p}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Composer({
  disabled,
  pendingConfirmation,
  isNew,
  onSend,
}: {
  disabled: boolean;
  pendingConfirmation: boolean;
  isNew: boolean;
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");

  function submit() {
    const value = text.trim();
    if (!value || disabled) return;
    setText("");
    onSend(value);
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="sticky bottom-[calc(4.25rem+env(safe-area-inset-bottom))] z-10 rounded-2xl border border-stone-300 bg-white p-2 shadow-sm sm:bottom-4 dark:border-stone-700 dark:bg-stone-900"
    >
      <label htmlFor="research-message" className="sr-only">
        Message
      </label>
      <div className="flex items-end gap-2">
        <textarea
          id="research-message"
          rows={2}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={
            disabled
              ? "Working on it…"
              : isNew
                ? "Describe what you need, e.g. headphones for flights under $400"
                : "Ask a follow-up, refine, or pick an option by number"
          }
          className="max-h-48 min-h-11 flex-1 resize-y bg-transparent px-2 py-1.5 outline-none disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>
      {pendingConfirmation && !disabled && (
        <p className="px-2 pt-1 text-xs text-stone-500 dark:text-stone-400">
          Sending a message cancels the tracking setup above.
        </p>
      )}
    </form>
  );
}
