const relative = new Intl.RelativeTimeFormat("en-CA", { numeric: "auto" });

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
];

/** "in 4 hours", "12 minutes ago", "just now", "in under a minute". */
export function fromNow(iso: string, now: number = Date.now()): string {
  const diff = new Date(iso).getTime() - now;
  for (const [unit, ms] of UNITS) {
    if (Math.abs(diff) >= ms) return relative.format(Math.round(diff / ms), unit);
  }
  return diff < 0 ? "just now" : "in under a minute";
}

/** "CA$399.00" (same style as the CLI and alerts; "US$" etc. for other currencies). */
export function formatPrice(amount: number, currency: string = "CAD"): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`; // unknown currency code
  }
}

/** "rtings.com" from a URL (no "www."). */
export function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
