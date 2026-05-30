// file: frontend/src/App.tsx
import React, { useState, useCallback, useRef, useEffect, lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, getApiKey } from './services/api';
import { useWebSocket } from './hooks/useWebSocket';
import { OverviewPage } from './components/overview/OverviewPage';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { StalenessIndicator } from './components/common/StalenessIndicator';
import { useAuth } from './components/auth/AuthContext';
import { LoginPage } from './components/auth/LoginPage';
import { AppShell } from './components/chrome/AppShell';

const HealthPage = lazy(() => import('./components/health/HealthPage').then(m => ({ default: m.HealthPage })));
const PortfolioPage = lazy(() => import('./components/portfolio/PortfolioPage').then(m => ({ default: m.PortfolioPage })));
const TradesPage = lazy(() => import('./components/trades/TradesPage').then(m => ({ default: m.TradesPage })));
const HistoryPage = lazy(() => import('./components/history/HistoryPage').then(m => ({ default: m.HistoryPage })));

const PageFallback = () => (
  <div className="flex items-center justify-center py-20 text-gray-500 text-sm">Loading…</div>
);

type Page = 'overview' | 'portfolio' | 'trades' | 'history' | 'health' | 'settings';

// Flush buffered WS data to React state at this rate (~4fps)
const WS_FLUSH_INTERVAL_MS = 250;

export default function App() {
  const { isAuthenticated } = useAuth();
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

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <div className="font-sans select-none bg-background text-foreground">
      <AppShell 
        currentPage={page} 
        onPageChange={(p) => setPage(p)} 
        wsLatencyMs={isConnected ? (Date.now() - (lastUpdateTs || Date.now())) : null}
      >
        <StalenessIndicator lastUpdateTs={lastUpdateTs} variant="banner" />

        {/* Content wrapper */}
        <div className="flex-1 flex flex-col min-h-0">
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
        {page === 'settings' && (
          <div className="p-4 sm:p-6 w-[90%] mx-auto flex-1 flex flex-col min-h-0">
            <ErrorBoundary resetKey={page}>
              <div className="text-sm text-fg3">Settings Page placeholder</div>
            </ErrorBoundary>
          </div>
        )}
        </div>
      </AppShell>
    </div>
  );
}
