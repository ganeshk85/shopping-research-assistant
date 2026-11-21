import type { ProductCandidate, ResearchComparison } from "@shopping-assistant/api-client";

import { ExternalLink } from "@/components/external-link";
import { formatPrice, hostname } from "@/lib/format";

/**
 * A comparison as numbered cards (US-37). The numbers match what the assistant expects
 * when you type "option 2". `onChoose` is only given for the latest comparison.
 */
export function ComparisonCards({
  comparison,
  onChoose,
  chosenName,
}: {
  comparison: ResearchComparison;
  onChoose?: (number: number, candidate: ProductCandidate) => void;
  chosenName?: string | null;
}) {
  // One link per site.
  const sources = (comparison.sources ?? [])
    .filter((url, i, all) => all.findIndex((u) => hostname(u) === hostname(url)) === i)
    .slice(0, 8);
  return (
    <section aria-label="Product comparison" className="space-y-4">
      <ol className="grid gap-3 lg:grid-cols-2">
        {comparison.candidates.map((c, i) => (
          <li key={`${i}-${c.name}`}>
            <CandidateCard
              number={i + 1}
              candidate={c}
              chosen={chosenName === c.name}
              onChoose={onChoose ? () => onChoose(i + 1, c) : undefined}
            />
          </li>
        ))}
      </ol>

      <div className="rounded-xl bg-emerald-50 p-4 text-sm leading-relaxed text-emerald-950 dark:bg-emerald-950/40 dark:text-emerald-100">
        <p className="font-semibold">Recommendation</p>
        <p>{comparison.recommendation_summary}</p>
      </div>

      {comparison.clarifying_question && <p className="text-sm">{comparison.clarifying_question}</p>}

      {sources.length > 0 && (
        <p className="text-xs text-stone-500 dark:text-stone-400">
          Based on:{" "}
          {sources.map((url, i) => (
              <span key={url}>
                {i > 0 && ", "}
                <ExternalLink href={url} className="underline decoration-stone-300 underline-offset-2 hover:text-stone-800 dark:hover:text-stone-200">
                  {hostname(url)}
                </ExternalLink>
              </span>
            ))}
        </p>
      )}
    </section>
  );
}

function CandidateCard({
  number,
  candidate: c,
  chosen,
  onChoose,
}: {
  number: number;
  candidate: ProductCandidate;
  chosen: boolean;
  onChoose?: () => void;
}) {
  const specs = c.key_specs ?? [];
  return (
    <article
      aria-label={`Option ${number}: ${c.name}`}
      className={`flex h-full flex-col gap-3 rounded-2xl border bg-white p-4 dark:bg-stone-900 ${
        chosen ? "border-emerald-500 ring-1 ring-emerald-500" : "border-stone-200 dark:border-stone-800"
      }`}
    >
      <header className="flex items-start gap-3">
        <span
          aria-hidden
          className="grid size-7 shrink-0 place-items-center rounded-full bg-stone-900 text-sm font-semibold text-white dark:bg-white dark:text-stone-900"
        >
          {number}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="leading-tight font-semibold">{c.name}</h3>
          <p className="text-sm text-stone-500 dark:text-stone-400">{c.brand}</p>
        </div>
        <p className="shrink-0 text-right">
          <span className="block text-xs text-stone-500 dark:text-stone-400">about</span>
          <span className="font-semibold tabular-nums">{formatPrice(c.estimated_price, c.currency)}</span>
        </p>
      </header>

      <p className="text-sm">
        <span className="font-medium">Best for:</span> {c.best_for}
      </p>
      <p className="text-sm text-stone-600 dark:text-stone-400">{c.rating_summary}</p>

      {specs.length > 0 && (
        <ul aria-label="Key specs" className="flex flex-wrap gap-1.5">
          {specs.map((s) => (
            <li key={s} className="rounded-md bg-stone-100 px-2 py-0.5 text-xs dark:bg-stone-800">
              {s}
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 text-sm sm:grid-cols-2">
        <List title="Pros" items={c.pros ?? []} mark="+" className="text-emerald-700 dark:text-emerald-400" />
        <List title="Cons" items={c.cons ?? []} mark="−" className="text-rose-700 dark:text-rose-400" />
      </div>

      {(onChoose || chosen) && (
        <div className="mt-auto pt-1">
          {chosen ? (
            <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">✓ Your choice</p>
          ) : (
            <button
              type="button"
              onClick={onChoose}
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium hover:border-stone-900 hover:bg-stone-900 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600 sm:w-auto dark:border-stone-700 dark:hover:border-white dark:hover:bg-white dark:hover:text-stone-900"
            >
              Choose this
            </button>
          )}
        </div>
      )}
    </article>
  );
}

function List({ title, items, mark, className }: { title: string; items: string[]; mark: string; className: string }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="mb-1 font-medium">{title}</p>
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item} className="flex gap-1.5">
            <span aria-hidden className={`font-semibold ${className}`}>
              {mark}
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
