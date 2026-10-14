/** The Say It Back mark: sound arcs coming in, an arrow going back out. Same drawing as favicon.svg. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" className={className}>
      <rect width="64" height="64" rx="18" className="fill-primary" />
      <path d="M20 26c-3.2 3.4-3.2 8.6 0 12" fill="none" strokeWidth="4" strokeLinecap="round" className="stroke-primary-container" />
      <path d="M27 21c-5.6 6.4-5.6 15.6 0 22" fill="none" strokeWidth="4" strokeLinecap="round" opacity=".7" className="stroke-primary-container" />
      <path d="M36 32h13m0 0-5-5m5 5-5 5" fill="none" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" className="stroke-on-primary" />
    </svg>
  )
}
