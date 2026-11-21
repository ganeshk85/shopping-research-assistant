"use client";

import { useEffect, useRef, useState } from "react";

import type { PriceHistory } from "@shopping-assistant/api-client";

import { formatPrice } from "@/lib/format";

const HEIGHT = 220;
const PAD = { top: 20, right: 16, bottom: 28, left: 64 };

const dateFormat = new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric" });
const dateTimeFormat = new Intl.DateTimeFormat("en-CA", { dateStyle: "medium", timeStyle: "short" });
// Compact for the table so a row fits on one line at phone width.
const rowFormat = new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** Round tick values for a y range: 3-5 "nice" steps (1, 2, 2.5 or 5 × 10^n). */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) return [min];
  const raw = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) ticks.push(Math.round(v * 100) / 100);
  return ticks;
}

/**
 * Price over time (US-40): one line, the target as a labelled reference line, the lowest
 * in-stock check marked, out-of-stock checks as hollow points. Hover shows a crosshair and
 * tooltip; the table below the chart (HistoryTable) carries every value as text.
 */
export function PriceHistoryChart({ history }: { history: PriceHistory }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const { entries, currency, target_price: target } = history;
  if (!entries.length) return <p className="text-sm text-stone-500">No price checks yet.</p>;

  const times = entries.map((e) => new Date(e.checked_at).getTime());
  const prices = entries.map((e) => e.price);
  let lo = Math.min(...prices, target);
  let hi = Math.max(...prices, target);
  const pad = (hi - lo || hi * 0.1 || 1) * 0.08;
  lo = Math.max(0, lo - pad);
  hi += pad;
  const t0 = times[0];
  const t1 = times.at(-1)!;

  const plotW = width - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const x = (t: number) => PAD.left + (t1 === t0 ? plotW / 2 : ((t - t0) / (t1 - t0)) * plotW);
  const y = (p: number) => PAD.top + (1 - (p - lo) / (hi - lo)) * plotH;
  const points = entries.map((e, i) => ({ ...e, cx: x(times[i]), cy: y(e.price) }));
  const line = points.map((p, i) => `${i ? "L" : "M"}${p.cx.toFixed(1)},${p.cy.toFixed(1)}`).join(" ");
  const lowest = points.find((p) => p.is_lowest);
  const outOfStock = points.some((p) => !p.in_stock);
  const ticks = niceTicks(lo, hi);
  const xLabels = t1 === t0 ? [t0] : [t0, t0 + (t1 - t0) / 2, t1];
  const active = hover === null ? null : points[hover];

  function onMove(event: React.PointerEvent<SVGRectElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * plotW + PAD.left;
    let best = 0;
    points.forEach((p, i) => {
      if (Math.abs(p.cx - px) < Math.abs(points[best].cx - px)) best = i;
    });
    setHover(best);
  }

  const summary =
    `Price history: ${entries.length} check(s) from ${dateFormat.format(t0)} to ${dateFormat.format(t1)}, ` +
    `latest ${formatPrice(prices.at(-1)!, currency)}, target ${formatPrice(target, currency)}` +
    (lowest ? `, lowest in stock ${formatPrice(lowest.price, currency)}.` : ".");

  return (
    <figure className="space-y-2">
      <div ref={box} className="relative w-full">
        <svg
          role="img"
          aria-label={summary}
          width={width}
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          className="block max-w-full overflow-visible text-stone-900 dark:text-stone-100"
        >
          {/* gridlines + y labels (recessive, solid hairlines) */}
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(t)}
                y2={y(t)}
                className="stroke-stone-200 dark:stroke-stone-800"
                strokeWidth={1}
              />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-stone-500 text-[11px] tabular-nums dark:fill-stone-400">
                {formatPrice(t, currency).replace(/\.00$/, "")}
              </text>
            </g>
          ))}
          {xLabels.map((t, i) => (
            <text
              key={i}
              x={x(t)}
              y={HEIGHT - 8}
              textAnchor={xLabels.length === 1 ? "middle" : i === 0 ? "start" : i === xLabels.length - 1 ? "end" : "middle"}
              className="fill-stone-500 text-[11px] dark:fill-stone-400"
            >
              {dateFormat.format(t)}
            </text>
          ))}

          {/* target reference line, labelled directly */}
          <line
            x1={PAD.left}
            x2={width - PAD.right}
            y1={y(target)}
            y2={y(target)}
            className="stroke-amber-600 dark:stroke-amber-400"
            strokeWidth={1.5}
          />
          <text x={width - PAD.right} y={y(target) - 6} textAnchor="end" className="fill-stone-700 text-[11px] font-medium dark:fill-stone-300">
            Target {formatPrice(target, currency)}
          </text>

          {/* the price line and its checks */}
          <path
            d={line}
            fill="none"
            className="stroke-emerald-600 dark:stroke-emerald-400"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {points.map((p) => (
            <circle
              key={p.id}
              cx={p.cx}
              cy={p.cy}
              r={p.is_lowest ? 6 : 4}
              strokeWidth={2}
              data-testid={p.in_stock ? "point-in-stock" : "point-out-of-stock"}
              className={
                p.in_stock
                  ? "fill-emerald-600 stroke-stone-50 dark:fill-emerald-400 dark:stroke-stone-950"
                  : "fill-stone-50 stroke-emerald-600 dark:fill-stone-950 dark:stroke-emerald-400"
              }
            />
          ))}
          {lowest && (
            <text
              x={Math.min(Math.max(lowest.cx, PAD.left + 40), width - PAD.right - 40)}
              y={lowest.cy + 20 > HEIGHT - PAD.bottom ? lowest.cy - 12 : lowest.cy + 20}
              textAnchor="middle"
              className="fill-stone-700 text-[11px] font-medium dark:fill-stone-300"
            >
              Lowest {formatPrice(lowest.price, currency)}
            </text>
          )}

          {/* hover layer: crosshair on the nearest check */}
          {active && (
            <line
              x1={active.cx}
              x2={active.cx}
              y1={PAD.top}
              y2={HEIGHT - PAD.bottom}
              className="stroke-stone-400 dark:stroke-stone-500"
              strokeWidth={1}
            />
          )}
          <rect
            x={PAD.left}
            y={PAD.top}
            width={plotW}
            height={plotH}
            fill="transparent"
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
          />
        </svg>

        {active && (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-10 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs shadow-md dark:border-stone-700 dark:bg-stone-900"
            style={{
              left: Math.min(Math.max(active.cx - 70, 0), width - 150),
              top: Math.max(active.cy - 64, 0),
            }}
          >
            <p className="font-semibold tabular-nums">{formatPrice(active.price, currency)}</p>
            <p className="text-stone-500 dark:text-stone-400">{dateTimeFormat.format(new Date(active.checked_at))}</p>
            <p>{active.in_stock ? "In stock" : "Out of stock"}</p>
          </div>
        )}
      </div>

      {outOfStock && (
        <figcaption className="flex gap-4 text-xs text-stone-600 dark:text-stone-400">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-full bg-emerald-600 dark:bg-emerald-400" /> In stock
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-full border-2 border-emerald-600 dark:border-emerald-400" /> Out
            of stock
          </span>
        </figcaption>
      )}
    </figure>
  );
}

/** Every check as text, oldest first (the chart's table view). */
export function HistoryTable({ history }: { history: PriceHistory }) {
  return (
    <div className="max-h-64 overflow-auto rounded-lg border border-stone-200 dark:border-stone-800">
      <table className="w-full text-sm">
        <caption className="sr-only">Every price check, oldest first</caption>
        <thead className="sticky top-0 bg-stone-100 text-left text-xs text-stone-600 dark:bg-stone-800 dark:text-stone-300">
          <tr>
            <th className="px-3 py-2 font-medium">Checked</th>
            <th className="px-3 py-2 text-right font-medium">Price</th>
            <th className="px-3 py-2 font-medium">Stock</th>
          </tr>
        </thead>
        <tbody>
          {history.entries.map((e) => (
            <tr key={e.id} className="border-t border-stone-100 whitespace-nowrap dark:border-stone-800">
              <td className="px-3 py-1.5" title={dateTimeFormat.format(new Date(e.checked_at))}>
                {rowFormat.format(new Date(e.checked_at))}
              </td>
              <td className="px-3 py-1.5 text-right tabular-nums">
                {formatPrice(e.price, history.currency)}
                {e.is_lowest && (
                  <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300">
                    lowest
                  </span>
                )}
              </td>
              <td className="px-3 py-1.5">{e.in_stock ? "In stock" : "Out of stock"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
