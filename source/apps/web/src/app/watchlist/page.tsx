import type { Metadata } from "next";

import { WatchlistApp } from "@/components/watchlist/watchlist-app";

export const metadata: Metadata = { title: "Watchlist" };

export default function WatchlistPage() {
  return <WatchlistApp />;
}
