"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";

import type { PriceHistory, WatchlistItem } from "@shopping-assistant/api-client";

import { ExternalLink } from "@/components/external-link";
import { errorMessage, watchlist } from "@/lib/api";
import { formatPrice, fromNow } from "@/lib/format";

import { CheckNow } from "./check-now";
import { HistoryTable, PriceHistoryChart } from "./price-history-chart";

/** Everything I track, with inline actions (US-39) and price history (US-40). */
export function WatchlistApp({ pollMs }: { pollMs?: number }) {
  const [items, setItems] = useState<WatchlistItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await watchlist.list());
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(load, 0);
    return () => clearTimeout(timer);
  }, [load]);

  const replace = (updated: WatchlistItem) => setItems((all) => all?.map((i) => (i.id === updated.id ? updated : i)) ?? null);
  const remove = (id: number) => setItems((all) => all?.filter((i) => i.id !== id) ?? null);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Watchlist</h1>
          <p className="max-w-prose text-stone-600 dark:text-stone-400">
            You&apos;re alerted when an in-stock price reaches your target or hits a new low.
          </p>
        </div>
        <CheckNow onFinished={load} pollMs={pollMs} />
      </div>

      {error && (
        <p role="alert" className="rounded-xl bg-rose-50 p-4 text-sm text-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
          {error}
        </p>
      )}

      {items === null && !error && <p className="text-sm text-stone-500">Loading your watchlist…</p>}

      {items?.length === 0 && (
        <div className="rounded-2xl border border-dashed border-stone-300 p-6 dark:border-stone-700">
          <p className="font-medium">Nothing tracked yet.</p>
          <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
            Research a product, choose one, and pick the listings to track.
          </p>
          <Link
            href="/research"
            className="mt-4 inline-block rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
          >
            Start researching
          </Link>
        </div>
      )}

      {items && items.length > 0 && (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id}>
              <ItemCard item={item} onChange={replace} onDeleted={remove} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ItemCard({
  item,
  onChange,
  onDeleted,
}: {
  item: WatchlistItem;
  onChange: (item: WatchlistItem) => void;
  onDeleted: (id: number) => void;
}) {
  const ids = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [targetText, setTargetText] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [history, setHistory] = useState<PriceHistory | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const cur = item.currency;
  const paused = item.status === "paused";
  const outOfStock = item.latest_in_stock === false;

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const toggleStatus = () =>
    run(async () => onChange(await watchlist.update(item.id, { status: paused ? "active" : "paused" })));

  function saveTarget(event: React.FormEvent) {
    event.preventDefault();
    const value = Number(targetText.replace(/[$,\s]/g, ""));
    if (!targetText.trim() || !Number.isFinite(value) || value <= 0) {
      setError("Enter a target price above zero.");
      return;
    }
    void run(async () => {
      onChange(await watchlist.update(item.id, { target_price: Math.round(value * 100) / 100 }));
      setEditing(false);
    });
  }

  const deleteItem = () =>
    run(async () => {
      await watchlist.remove(item.id);
      onDeleted(item.id);
    });

  function toggleHistory() {
    const open = !showHistory;
    setShowHistory(open);
    if (open) void run(async () => setHistory(await watchlist.history(item.id)));
  }

  return (
    <article
      aria-labelledby={`${ids}-name`}
      className={`rounded-2xl border bg-white p-4 dark:bg-stone-900 ${
        item.needs_attention ? "border-amber-300 dark:border-amber-700/60" : "border-stone-200 dark:border-stone-800"
      } ${paused ? "opacity-80" : ""}`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 id={`${ids}-name`} className="leading-tight font-semibold">
            {item.product_name}
          </h2>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-stone-600 dark:text-stone-400">
            <ExternalLink href={item.url} className="font-medium text-emerald-700 hover:underline dark:text-emerald-400">
              {item.retailer} ↗
            </ExternalLink>
            <StatusBadge paused={paused} />
            {cur !== "CAD" && (
              <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900/50 dark:text-amber-200">
                Priced in {cur}
              </span>
            )}
          </p>
        </div>

        <dl className="grid grid-cols-3 gap-4 text-sm sm:text-right">
          <Stat label="Latest">
            {item.latest_price == null ? "—" : formatPrice(item.latest_price, cur)}
            {outOfStock && <span className="block text-xs font-medium text-amber-700 dark:text-amber-300">Out of stock</span>}
          </Stat>
          <Stat label="Lowest">{formatPrice(item.lowest_price_seen, cur)}</Stat>
          <Stat label="Target">{formatPrice(item.target_price, cur)}</Stat>
        </dl>
      </div>

      <p className="mt-2 text-xs text-stone-500 dark:text-stone-400">
        {item.last_checked_at ? `Checked ${fromNow(item.last_checked_at)}` : "Not checked yet"}
      </p>

      {item.needs_attention && (
        <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          <span aria-hidden>⚠ </span>
          The last {item.consecutive_failures} checks failed
          {item.last_check_error ? ` (${item.last_check_error})` : ""}. The retailer may be blocking checks; consider
          pausing this item.
        </p>
      )}

      {editing ? (
        <form onSubmit={saveTarget} className="mt-3 flex flex-wrap items-center gap-2">
          <label htmlFor={`${ids}-target`} className="text-sm font-medium">
            New target
          </label>
          <input
            id={`${ids}-target`}
            inputMode="decimal"
            autoFocus
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            className="w-28 rounded-lg border border-stone-300 bg-transparent px-2 py-1.5 text-sm tabular-nums dark:border-stone-700"
          />
          <Button type="submit" disabled={busy} primary>
            Save
          </Button>
          <Button onClick={() => setEditing(false)} disabled={busy}>
            Cancel
          </Button>
        </form>
      ) : confirmDelete ? (
        <div role="alertdialog" aria-labelledby={`${ids}-del`} className="mt-3 rounded-lg bg-rose-50 p-3 text-sm dark:bg-rose-950/40">
          <p id={`${ids}-del`} className="font-medium text-rose-900 dark:text-rose-100">
            Delete {item.product_name} at {item.retailer} and its price history? This can&apos;t be undone.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={deleteItem}
              disabled={busy}
              className="rounded-lg bg-rose-700 px-3 py-1.5 font-medium text-white hover:bg-rose-800 disabled:opacity-60"
            >
              Delete
            </button>
            <Button onClick={() => setConfirmDelete(false)} disabled={busy}>
              Keep it
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button onClick={toggleStatus} disabled={busy}>
            {paused ? "Resume" : "Pause"}
          </Button>
          <Button
            onClick={() => {
              setTargetText(item.target_price.toFixed(2));
              setEditing(true);
            }}
            disabled={busy}
          >
            Edit target
          </Button>
          <Button onClick={toggleHistory} disabled={busy} expanded={showHistory}>
            {showHistory ? "Hide history" : "Price history"}
          </Button>
          <Button onClick={() => setConfirmDelete(true)} disabled={busy}>
            Delete
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-2 text-sm font-medium text-rose-700 dark:text-rose-400">
          {error}
        </p>
      )}

      {showHistory && history && (
        <div className="mt-4 space-y-3">
          <PriceHistoryChart history={history} />
          <HistoryTable history={history} />
        </div>
      )}
    </article>
  );
}

function StatusBadge({ paused }: { paused: boolean }) {
  return (
    <span
      className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${
        paused
          ? "bg-stone-200 text-stone-700 dark:bg-stone-800 dark:text-stone-300"
          : "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300"
      }`}
    >
      {paused ? "Paused" : "Active"}
    </span>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-stone-500 dark:text-stone-400">{label}</dt>
      <dd className="font-semibold tabular-nums">{children}</dd>
    </div>
  );
}

function Button({
  children,
  onClick,
  disabled,
  primary,
  expanded,
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  primary?: boolean;
  expanded?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      aria-expanded={expanded}
      className={
        primary
          ? "rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
          : "rounded-lg border border-stone-300 px-3 py-1.5 text-sm font-medium hover:bg-stone-100 disabled:opacity-60 dark:border-stone-700 dark:hover:bg-stone-800"
      }
    >
      {children}
    </button>
  );
}
