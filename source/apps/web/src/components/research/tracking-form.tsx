"use client";

import { useId, useState } from "react";

import type { ConfirmTracking, PendingConfirmation } from "@shopping-assistant/api-client";

import { formatPrice } from "@/lib/format";

import { ListingDetails } from "./listings";

/** Same rule as the backend (BRL-3): `discount` below the cheapest selected price, to the cent. */
export function suggestedTarget(prices: number[], discount: number): number {
  return Math.round(Math.min(...prices) * (1 - discount) * 100) / 100;
}

/**
 * Choose listings and a target price (US-38). Nothing is saved until Confirm;
 * Cancel saves nothing. Server-side validation errors are shown via `error`.
 */
export function TrackingForm({
  pending,
  busy,
  error,
  onSubmit,
}: {
  pending: PendingConfirmation;
  busy: boolean;
  error: string | null;
  onSubmit: (decision: ConfirmTracking) => void;
}) {
  const ids = useId();
  const [selected, setSelected] = useState<number[]>([]);
  const [target, setTarget] = useState<string | null>(null); // null = follow the suggestion
  const [problem, setProblem] = useState<string | null>(null);

  const listings = pending.listings;
  const currency = listings[0]?.currency ?? "CAD";
  const chosenPrices = selected.map((n) => listings[n - 1].current_price);
  const suggestion = chosenPrices.length ? suggestedTarget(chosenPrices, pending.discount) : pending.suggested_target;
  const targetText = target ?? suggestion.toFixed(2);
  const cheapest = chosenPrices.length ? Math.min(...chosenPrices) : null;
  const targetValue = Number(targetText);
  const aboveCurrent = cheapest !== null && Number.isFinite(targetValue) && targetValue >= cheapest;

  function toggle(n: number) {
    setProblem(null);
    setSelected((s) => (s.includes(n) ? s.filter((x) => x !== n) : [...s, n].sort((a, b) => a - b)));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!selected.length) return setProblem("Tick at least one listing to track.");
    const value = Number(targetText.replace(/[$,\s]/g, ""));
    if (!targetText.trim() || !Number.isFinite(value) || value <= 0) {
      return setProblem("Enter a target price above zero, e.g. 349.99.");
    }
    setProblem(null);
    onSubmit({ action: "track", selected, target_price: Math.round(value * 100) / 100 });
  }

  const message = problem ?? error;
  return (
    <form
      onSubmit={submit}
      aria-labelledby={`${ids}-title`}
      className="space-y-4 rounded-2xl border border-emerald-300 bg-white p-4 shadow-sm dark:border-emerald-800 dark:bg-stone-900"
    >
      <div>
        <h3 id={`${ids}-title`} className="font-semibold">
          Track the price of {pending.product_name}
        </h3>
        <p className="text-sm text-stone-600 dark:text-stone-400">
          Choose the listings to watch and the price you&apos;d like to be alerted at. Nothing is saved until you
          confirm.
        </p>
      </div>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium">Listings</legend>
        {listings.map((l, i) => {
          const n = i + 1;
          return (
            <label
              key={l.url}
              className="flex cursor-pointer gap-3 rounded-xl border border-stone-200 p-3 text-sm has-checked:border-emerald-500 has-checked:bg-emerald-50/60 dark:border-stone-800 dark:has-checked:bg-emerald-950/30"
            >
              <input
                type="checkbox"
                checked={selected.includes(n)}
                onChange={() => toggle(n)}
                disabled={busy}
                aria-label={`Track ${l.retailer} at ${formatPrice(l.current_price, l.currency)}`}
                className="mt-1 size-4 shrink-0 accent-emerald-600"
              />
              <ListingDetails listing={l} />
            </label>
          );
        })}
      </fieldset>

      <div className="space-y-1">
        <label htmlFor={`${ids}-target`} className="text-sm font-medium">
          Alert me at or below
        </label>
        <div className="flex max-w-xs items-center rounded-lg border border-stone-300 focus-within:ring-2 focus-within:ring-emerald-600 dark:border-stone-700">
          <span className="pl-3 text-sm text-stone-500">{currency === "CAD" ? "CA$" : currency}</span>
          <input
            id={`${ids}-target`}
            inputMode="decimal"
            value={targetText}
            onChange={(e) => {
              setProblem(null);
              setTarget(e.target.value);
            }}
            disabled={busy}
            aria-describedby={`${ids}-target-help`}
            className="w-full bg-transparent px-2 py-2 tabular-nums outline-none"
          />
        </div>
        <p id={`${ids}-target-help`} className="text-xs text-stone-500 dark:text-stone-400">
          Suggested: {formatPrice(suggestion, currency)}, {Math.round(pending.discount * 100)}% below the cheapest
          {selected.length ? " selected" : ""} listing.
          {target !== null && (
            <>
              {" "}
              <button type="button" className="underline" onClick={() => setTarget(null)} disabled={busy}>
                Use suggestion
              </button>
            </>
          )}
        </p>
        {aboveCurrent && (
          <p className="text-xs text-amber-700 dark:text-amber-300">
            That&apos;s at or above the current price, so you&apos;ll be alerted at the next check.
          </p>
        )}
      </div>

      {message && (
        <p role="alert" className="text-sm font-medium text-rose-700 dark:text-rose-400">
          {message}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
        >
          {busy ? "Saving…" : `Start tracking${selected.length ? ` (${selected.length})` : ""}`}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onSubmit({ action: "cancel", selected: [] })}
          className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium hover:bg-stone-100 disabled:opacity-60 dark:border-stone-700 dark:hover:bg-stone-800"
        >
          Don&apos;t track
        </button>
      </div>
    </form>
  );
}
