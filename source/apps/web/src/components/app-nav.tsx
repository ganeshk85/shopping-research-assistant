"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/research", label: "Research", icon: ChatIcon },
  { href: "/watchlist", label: "Watchlist", icon: ListIcon },
  { href: "/settings", label: "Settings", icon: BellIcon },
] as const;

function useActive() {
  const pathname = usePathname();
  return (href: string) => pathname === href || pathname.startsWith(`${href}/`);
}

/** Top bar: brand plus links on wider screens. */
export function AppHeader() {
  const isActive = useActive();
  return (
    <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/85 backdrop-blur dark:border-stone-800 dark:bg-stone-950/85">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4 sm:px-6">
        <Link href="/research" className="flex items-center gap-2 font-semibold tracking-tight">
          <span aria-hidden className="grid size-7 place-items-center rounded-lg bg-emerald-600 text-sm text-white">
            ↓
          </span>
          <span>Shopping Assistant</span>
        </Link>
        <nav aria-label="Main" className="hidden gap-1 sm:flex">
          {NAV.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-stone-600 hover:bg-stone-100 hover:text-stone-900 aria-[current=page]:bg-stone-900 aria-[current=page]:text-white dark:text-stone-300 dark:hover:bg-stone-800 dark:hover:text-white dark:aria-[current=page]:bg-white dark:aria-[current=page]:text-stone-900"
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}

/** Bottom tab bar at phone width. */
export function MobileTabBar() {
  const isActive = useActive();
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-20 border-t border-stone-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden dark:border-stone-800 dark:bg-stone-950/95"
    >
      <ul className="grid grid-cols-3">
        {NAV.map(({ href, label, icon: Icon }) => (
          <li key={href}>
            <Link
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className="flex flex-col items-center gap-0.5 py-2 text-xs font-medium text-stone-500 aria-[current=page]:text-emerald-700 dark:text-stone-400 dark:aria-[current=page]:text-emerald-400"
            >
              <Icon />
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function ChatIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinejoin="round" d="M4 5h16v11H9l-5 4V5z" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinejoin="round" d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2zM10 20a2 2 0 0 0 4 0" />
    </svg>
  );
}
