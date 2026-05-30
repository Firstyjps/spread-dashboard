import { useEffect, useMemo, useState } from 'react';

interface StalenessIndicatorProps {
  lastUpdateTs: number | null;
  variant?: 'compact' | 'banner';
}

export function StalenessIndicator({ lastUpdateTs, variant = 'compact' }: StalenessIndicatorProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const ageS = useMemo(() => {
    if (!lastUpdateTs) return null;
    return Math.max(0, Math.floor((now - lastUpdateTs) / 1000));
  }, [lastUpdateTs, now]);

  const isStale = ageS != null && ageS > 10;
  const isCritical = ageS != null && ageS > 30;

  if (variant === 'banner') {
    if (!isCritical) return null;
    return (
      <div className="border-b border-short/40 bg-short/10 px-4 py-2 text-center text-xs font-semibold text-short">
        Feed stale for {ageS}s. Executions may be blocked by the circuit breaker.
      </div>
    );
  }

  const label = ageS == null
    ? 'No ts'
    : isStale
      ? `⚠ STALE ${ageS}s`
      : `Updated ${ageS}s ago`;

  return (
    <span
      className={`inline-flex items-center gap-1 border-l border-bd1 pl-2 ${
        isStale ? 'text-short' : 'text-fg3'
      }`}
    >
      {label}
    </span>
  );
}
