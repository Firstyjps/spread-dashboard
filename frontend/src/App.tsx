// file: frontend/src/App.tsx
import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from './services/api';
import { useWebSocket } from './hooks/useWebSocket';
import { OverviewPage } from './components/overview/OverviewPage';
import { HealthPage } from './components/health/HealthPage';

type Page = 'overview' | 'health';

// Flush buffered WS data to React state at this rate (~4fps)
const WS_FLUSH_INTERVAL_MS = 250;

export default function App() {
  const [page, setPage] = useState<Page>('overview');
  const [wsData, setWsData] = useState<any>(null);

  // Buffer: WS messages write here without triggering renders
  const wsBufferRef = useRef<any>(null);
  const hasPendingRef = useRef(false);

  // Flush timer: transfers buffer → state at a fixed rate
  useEffect(() => {
    const timer = setInterval(() => {
      if (hasPendingRef.current) {
        hasPendingRef.current = false;
        setWsData(wsBufferRef.current);
      }
    }, WS_FLUSH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  const handleWsMessage = useCallback((msg: unknown) => {
    const m = msg as { type?: string; data?: Record<string, unknown> };
    if (m.type === 'update' || m.type === 'snapshot') {
      wsBufferRef.current = m.data ?? null;
      hasPendingRef.current = true;
    }
  }, []);

  const { isConnected, subscribe, unsubscribe } = useWebSocket({
    url: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`,
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
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Nav */}
      <nav className="border-b border-gray-800 px-6 py-3 flex items-center gap-6">
        <h1 className="text-lg font-bold text-emerald-400">Spread Dashboard</h1>
        <div className="flex gap-2">
          <NavBtn active={page === 'overview'} onClick={() => setPage('overview')}>
            Overview
          </NavBtn>
          <NavBtn active={page === 'health'} onClick={() => setPage('health')}>
            Health
          </NavBtn>
        </div>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              isConnected ? 'bg-emerald-400' : 'bg-red-400'
            }`}
          />
          <span className="text-gray-400">{isConnected ? 'Live' : 'Polling'}</span>
        </div>
      </nav>

      {/* Content */}
      <main className="p-6">
        {page === 'overview' && <OverviewPage data={priceData} />}
        {page === 'health' && <HealthPage />}
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
      className={`px-3 py-1 rounded text-sm transition ${
        active ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'
      }`}
    >
      {children}
    </button>
  );
}
