import type { Metadata, Viewport } from "next";

import { AppHeader, MobileTabBar } from "@/components/app-nav";
import { BackendStatus } from "@/components/backend-status";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Shopping Assistant", template: "%s · Shopping Assistant" },
  description: "Research the best product for a need, then track its price at Canadian retailers.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafaf9" },
    { media: "(prefers-color-scheme: dark)", color: "#0c0a09" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-CA" className="h-full">
      <body className="flex min-h-full flex-col">
        <AppHeader />
        <BackendStatus />
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pt-6 pb-24 sm:px-6 sm:pb-12">{children}</main>
        <MobileTabBar />
      </body>
    </html>
  );
}
