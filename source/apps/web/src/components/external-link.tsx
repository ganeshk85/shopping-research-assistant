/**
 * Every link to a retailer or source goes through here (US-42): it opens in a new tab and
 * shares nothing with the opened page. The app only links out; it never buys anything.
 */
export function ExternalLink({
  href,
  children,
  className,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}
