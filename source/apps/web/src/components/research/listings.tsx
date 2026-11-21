import type { RetailListing } from "@shopping-assistant/api-client";

import { ExternalLink } from "@/components/external-link";
import { formatPrice } from "@/lib/format";

/** Retailer, price, stock, verified/estimated label and a link out (US-38, US-42). */
export function ListingDetails({ listing: l }: { listing: RetailListing }) {
  return (
    <div className="min-w-0 flex-1">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="font-medium">{l.retailer}</span>
        <span className="font-semibold tabular-nums">{formatPrice(l.current_price, l.currency)}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
        <Badge tone={l.in_stock ? "good" : "warn"}>{l.in_stock ? "In stock" : "Out of stock"}</Badge>
        <Badge tone={l.price_verified ? "good" : "muted"}>
          {l.price_verified ? "Verified price" : "Estimated price"}
        </Badge>
        {l.currency !== "CAD" && <Badge tone="warn">{l.currency}</Badge>}
        <ExternalLink
          href={l.url}
          className="ml-auto font-medium text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-400"
        >
          View at {l.retailer} ↗
        </ExternalLink>
      </div>
      {l.note && <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">{l.note}</p>}
    </div>
  );
}

/** Listings shown earlier in a conversation (read-only). */
export function ListingList({ listings }: { listings: RetailListing[] }) {
  return (
    <ol aria-label="Retailer listings" className="space-y-2">
      {listings.map((l, i) => (
        <li
          key={l.url}
          className="flex gap-3 rounded-xl border border-stone-200 bg-white p-3 text-sm dark:border-stone-800 dark:bg-stone-900"
        >
          <span aria-hidden className="w-5 shrink-0 pt-0.5 text-stone-400">
            {i + 1}.
          </span>
          <ListingDetails listing={l} />
        </li>
      ))}
    </ol>
  );
}

function Badge({ tone, children }: { tone: "good" | "warn" | "muted"; children: React.ReactNode }) {
  const tones = {
    good: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300",
    warn: "bg-amber-100 text-amber-900 dark:bg-amber-900/50 dark:text-amber-200",
    muted: "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300",
  };
  return <span className={`rounded-md px-1.5 py-0.5 font-medium ${tones[tone]}`}>{children}</span>;
}
