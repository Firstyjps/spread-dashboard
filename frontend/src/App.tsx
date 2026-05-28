// file: frontend/src/App.tsx
import React, { useState, useCallback, useRef, useEffect, lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, getApiKey } from './services/api';
import { useWebSocket } from './hooks/useWebSocket';
import { OverviewPage } from './components/overview/OverviewPage';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { StalenessIndicator } from './components/common/StalenessIndicator';

const HealthPage = lazy(() => import('./components/health/HealthPage').then(m => ({ default: m.HealthPage })));
const PortfolioPage = lazy(() => import('./components/portfolio/PortfolioPage').then(m => ({ default: m.PortfolioPage })));
const TradesPage = lazy(() => import('./components/trades/TradesPage').then(m => ({ default: m.TradesPage })));
const HistoryPage = lazy(() => import('./components/history/HistoryPage').then(m => ({ default: m.HistoryPage })));

const PageFallback = () => (
  <div className="flex items-center justify-center py-20 text-gray-500 text-sm">Loading…</div>
);

type Page = 'overview' | 'portfolio' | 'trades' | 'history' | 'health';

// Flush buffered WS data to React state at this rate (~4fps)
const WS_FLUSH_INTERVAL_MS = 250;

export default function App() {
  const [page, setPage] = useState<Page>('overview');
  const [wsData, setWsData] = useState<any>(null);
  const [lastUpdateTs, setLastUpdateTs] = useState<number | null>(null);

  // Buffer: WS messages write here without triggering renders
  const wsBufferRef = useRef<any>(null);
  const wsTsBufferRef = useRef<number | null>(null);
  const hasPendingRef = useRef(false);

  // Flush timer: transfers buffer → state at a fixed rate
  useEffect(() => {
    const timer = setInterval(() => {
      if (hasPendingRef.current) {
        hasPendingRef.current = false;
        setWsData(wsBufferRef.current);
        setLastUpdateTs(wsTsBufferRef.current);
      }
    }, WS_FLUSH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  const handleWsMessage = useCallback((msg: unknown) => {
    const m = msg as { type?: string; data?: Record<string, unknown>; ts?: number };
    if (m.type === 'update' || m.type === 'snapshot') {
      wsBufferRef.current = m.data ?? null;
      wsTsBufferRef.current = typeof m.ts === 'number' ? m.ts : Date.now();
      hasPendingRef.current = true;
    }
  }, []);

  const { isConnected, subscribe, unsubscribe } = useWebSocket({
    url: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws${getApiKey() ? `?token=${encodeURIComponent(getApiKey())}` : ''}`,
    onMessage: handleWsMessage,
  });

  // Fallback REST polling (only active when WS is disconnected)
  const { data: restData } = useQuery({
    queryKey: ['prices'],
    queryFn: api.prices,
    enabled: !isConnected,
    refetchInterval: 2000,
    staleTime: 1000,
  });

  const priceData = wsData || restData;

  return (
    <div className="min-h-screen bg-brand-base text-text-primary flex flex-col font-sans select-none">
      {/* Sticky Topbar */}
      <nav className="sticky top-0 z-40 bg-brand-base/80 backdrop-blur-md border-b border-border-subtle h-11 sm:h-12 flex items-center px-2 sm:px-4 justify-between overflow-hidden">
        <div className="flex min-w-0 flex-1 items-center justify-center sm:flex-none sm:justify-start sm:gap-6">
          {/* Logo */}
          <div className="hidden sm:flex shrink-0 items-center gap-1.5 cursor-pointer" onClick={() => setPage('overview')}>
            <div className="w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-sm bg-gradient-to-tr from-accent-amber to-accent-indigo shadow-[0_0_10px_rgba(245,166,35,0.4)]" />
            <span className="font-mono font-bold text-[11px] sm:text-xs tracking-wider text-text-primary">
              spread<span className="text-accent-amber">.</span>dash
            </span>
          </div>

          {/* Navigation Tabs */}
          <div className="grid h-11 w-full min-w-0 grid-cols-4 items-center sm:flex sm:h-12 sm:w-auto sm:justify-start">
            <NavBtn active={page === 'overview'} onClick={() => setPage('overview')}>
              Overview
            </NavBtn>
            <NavBtn active={page === 'portfolio'} onClick={() => setPage('portfolio')}>
              Portfolio
            </NavBtn>
            <NavBtn active={page === 'trades'} onClick={() => setPage('trades')}>
              Trades
            </NavBtn>
            <NavBtn active={page === 'history'} onClick={() => setPage('history')}>
              History
            </NavBtn>
            <div className="hidden sm:block">
              <NavBtn active={page === 'health'} onClick={() => setPage('health')}>
                Health
              </NavBtn>
            </div>
          </div>
        </div>

        {/* Live status dot */}
        <div className="hidden sm:flex items-center gap-2 text-xs font-mono bg-brand-panel/40 border border-border-subtle px-2 py-0.5 rounded-md">
          <span className="relative flex h-1.5 w-1.5">
            {isConnected && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-green opacity-75"></span>
            )}
            <span
              className={`relative inline-flex rounded-full h-1.5 w-1.5 ${
                isConnected ? 'bg-accent-green' : 'bg-accent-red animate-pulse-slow'
              }`}
            />
          </span>
          <span className="text-text-secondary font-mono tracking-tight text-[10px]">
            {isConnected ? 'LIVE FEED' : 'REST POLLING'}
          </span>
          <StalenessIndicator lastUpdateTs={lastUpdateTs} />
        </div>
      </nav>
      <StalenessIndicator lastUpdateTs={lastUpdateTs} variant="banner" />

      {/* Content wrapper */}
      <main className="flex-1 flex flex-col min-h-0">
        {page === 'overview' && (
          <ErrorBoundary resetKey={page}>
            <OverviewPage data={priceData} />
          </ErrorBoundary>
        )}
        {page === 'portfolio' && (
          <div className="p-4 sm:p-6 w-[90%] mx-auto flex-1 flex flex-col min-h-0">
            <ErrorBoundary resetKey={page}>
              <Suspense fallback={<PageFallback />}>
                <PortfolioPage />
              </Suspense>
            </ErrorBoundary>
          </div>
        )}
        {page === 'trades' && (
          <div className="p-4 sm:p-6 w-[90%] mx-auto flex-1 flex flex-col min-h-0">
            <ErrorBoundary resetKey={page}>
              <Suspense fallback={<PageFallback />}>
                <TradesPage />
              </Suspense>
            </ErrorBoundary>
          </div>
        )}
        {page === 'history' && (
          <div className="p-4 sm:p-6 w-[90%] mx-auto flex-1 flex flex-col min-h-0">
            <ErrorBoundary resetKey={page}>
              <Suspense fallback={<PageFallback />}>
                <HistoryPage />
              </Suspense>
            </ErrorBoundary>
          </div>
        )}
        {page === 'health' && (
          <div className="p-4 sm:p-6 w-[90%] mx-auto flex-1 flex flex-col min-h-0">
            <ErrorBoundary resetKey={page}>
              <Suspense fallback={<PageFallback />}>
                <HealthPage />
              </Suspense>
            </ErrorBoundary>
          </div>
        )}
      </main>
    </div>
  );
}

function NavBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex h-11 w-full items-center justify-center px-0.5 text-[11px] font-semibold border-b-2 transition-colors duration-150 whitespace-nowrap sm:h-12 sm:w-auto sm:px-3 sm:text-xs sm:font-medium ${
        active
          ? 'border-accent-amber text-text-primary'
          : 'border-transparent text-text-secondary hover:text-text-primary hover:border-border-strong'
      }`}
    >
      {children}
    </button>
  );
}
