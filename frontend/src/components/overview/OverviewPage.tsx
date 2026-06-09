// file: frontend/src/components/overview/OverviewPage.tsx
import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';
import { SpreadChart } from './SpreadChart';
import { ExecutionPanel } from './ExecutionPanel';
import { AutoHedgePanel } from './AutoHedgePanel';
import type { SymbolDataMap, Alert } from '../../types/api';

interface Props {
  data: SymbolDataMap | null;
}

interface Toast {
  id: string;
  message: string;
  type: 'success' | 'info' | 'error';
}

export const OverviewPage = React.memo(function OverviewPage({ data }: Props) {
  const { data: fundingData } = useQuery({
    queryKey: ['funding'],
    queryFn: api.funding,
    refetchInterval: 30000,
    staleTime: 25000,
  });

  const { data: alertsData } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => api.alerts(20),
    refetchInterval: 10000,
    staleTime: 8000,
  });

  // Extract all symbols
  const allSymbols = useMemo(() => (data ? Object.keys(data) : []), [data]);

  // Active symbol context state
  const [activeSymbol, setActiveSymbol] = useState<string>('');
  const [clearedAt, setClearedAt] = useState<number | null>(null);

  // Fallback to first symbol
  useEffect(() => {
    if (allSymbols.length > 0) {
      if (!activeSymbol || !allSymbols.includes(activeSymbol)) {
        if (allSymbols.includes('XAUTUSDT')) {
          setActiveSymbol('XAUTUSDT');
        } else {
          setActiveSymbol(allSymbols[0]);
        }
      }
    }
  }, [allSymbols, activeSymbol]);

  // Toast notifications state
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: 'success' | 'info' | 'error' = 'success') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 2500);
  }, []);

  // Keyboard shortcut executors
  const executionPanelRef = useRef<{ executeBuy: () => void; executeSell: () => void } | null>(null);

  const handleBuyShortcut = useCallback(() => {
    if (executionPanelRef.current) executionPanelRef.current.executeBuy();
  }, []);

  const handleSellShortcut = useCallback(() => {
    if (executionPanelRef.current) executionPanelRef.current.executeSell();
  }, []);

  // Set up keyboard listeners (B / S keys)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        return;
      }
      const key = e.key.toUpperCase();
      if (key === 'B') {
        e.preventDefault();
        handleBuyShortcut();
      } else if (key === 'S') {
        e.preventDefault();
        handleSellShortcut();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleBuyShortcut, handleSellShortcut]);

  if (!data) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[400px] text-fg2">
        <div className="text-center space-y-3">
          <div className="w-8 h-8 rounded-full border-2 border-warn/30 border-t-warn animate-spin mx-auto" />
          <p className="text-xs font-mono tracking-tight text-fg3">CONNECTING TO EXCHANGES...</p>
        </div>
      </div>
    );
  }

  const activeData = data[activeSymbol];
  const spread = activeData?.spread;
  const spreadBpsVal = spread ? spread.exchange_spread_mid * 10000 : null;
  const spreadBps = spreadBpsVal != null ? spreadBpsVal.toFixed(2) : '-';
  
  const bybitMid = activeData?.bybit?.mid;
  const lighterMid = activeData?.lighter?.mid;
  
  const longBps = spread ? (spread.long_spread * 10000).toFixed(2) : '-';
  const shortBps = spread ? (spread.short_spread * 10000).toFixed(2) : '-';
  const baBybit = spread ? (spread.bid_ask_spread_bybit * 10000).toFixed(2) : '-';
  const baLighter = spread ? (spread.bid_ask_spread_lighter * 10000).toFixed(2) : '-';
  const netPnl = activeData?.net_pnl_bps;
  const latBybit = activeData?.latency_bybit != null ? Math.round(activeData.latency_bybit) : null;
  const latLighter = activeData?.latency_lighter != null ? Math.round(activeData.latency_lighter) : null;

  // Active Symbol's Funding
  const activeFunding = fundingData?.[activeSymbol];
  const bybitFunding = activeFunding?.bybit?.funding_rate;
  const lighterFunding = activeFunding?.lighter?.funding_rate;

  const bybitAnnualized = bybitFunding != null ? bybitFunding * 3 * 365 : null;
  const lighterAnnualized = lighterFunding != null ? lighterFunding * 24 * 365 : null;
  const netFundingAnnualized = (bybitAnnualized != null && lighterAnnualized != null)
    ? (lighterAnnualized - bybitAnnualized)
    : null;

  // Countdown for next funding
  const nextFundingMs = activeFunding?.bybit?.next_funding_time;
  const countdown = nextFundingMs ? Math.max(0, nextFundingMs - Date.now()) : null;
  const countdownMin = countdown != null ? Math.floor(countdown / 60000) : null;

  return (
    <div className="flex-1 flex flex-col lg:flex-row min-h-0 divide-y lg:divide-y-0 lg:divide-x divide-bd1">
      {/* 1. MAIN CONTENT (Flex: 1) */}
      <section className="flex-1 min-w-0 bg-bg1 flex flex-col p-4 sm:p-6 overflow-y-auto space-y-6">
        {/* Compact Auto-Hedge row */}
        <div className="hidden lg:block">
          <AutoHedgePanel />
        </div>

        {/* Hero Spread Card */}
        <div className="bg-card border border-bd1 rounded-lg p-5 relative overflow-hidden flex flex-col">
          {/* Top Amber gradient accent line */}
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-warn to-transparent opacity-80" />

          {/* Label Header row */}
          <div className="grid grid-cols-3 text-center mb-3">
            <div className="text-left">
              <span className="text-[10px] font-bold text-fg3 uppercase tracking-wider">Bybit Mid</span>
            </div>
            <div>
              <span className="text-[10px] font-bold text-warn uppercase tracking-wider font-mono">SPREAD (bps)</span>
            </div>
            <div className="text-right">
              <span className="text-[10px] font-bold text-info uppercase tracking-wider">Lighter Mid</span>
            </div>
          </div>

          {/* Main Price display row */}
          <div className="grid grid-cols-3 items-center text-center py-2 border-b border-bd1/50 pb-4 mb-4">
            {/* Bybit Mid Price */}
            <div className="text-left font-mono">
              <div className="text-xl sm:text-2xl font-bold text-fg1">
                {bybitMid ? bybitMid.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
              </div>
              <div className="text-[10px] text-fg2/70 mt-1">
                B/A: <span className="text-fg1 font-bold">{baBybit}</span> bps
              </div>
            </div>

            {/* Pulsing Spread Mid */}
            <div className="flex flex-col items-center justify-center">
              {/* Force React remounting on spread update to trigger the 120ms tick animation */}
              <div
                key={`${activeSymbol}-${spreadBps}`}
                className="text-3xl sm:text-4xl md:text-5xl font-mono font-black text-warn animate-tick drop-shadow-[0_0_16px_rgba(245,166,35,0.2)]"
              >
                {spreadBps}
              </div>
              <div className="text-[9px] text-fg3 font-bold tracking-widest mt-1">REALTIME</div>
            </div>

            {/* Lighter Mid Price */}
            <div className="text-right font-mono">
              <div className="text-xl sm:text-2xl font-bold text-info">
                {lighterMid ? lighterMid.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
              </div>
              <div className="text-[10px] text-fg2/70 mt-1">
                B/A: <span className="text-info font-bold">{baLighter}</span> bps
              </div>
            </div>
          </div>

          {/* Bottom row metrics */}
          <div className="grid grid-cols-3 text-xs font-mono">
            <div className="text-left">
              <span className="text-fg3 text-[10px]">Long spread</span>
              <div className="text-accent-indigo font-bold text-sm mt-0.5">{longBps} bps</div>
            </div>
            <div className="text-center flex flex-col items-center">
              <span className="text-fg3 text-[10px]">Net Arbitrage PnL</span>
              <div
                className={`font-black text-sm mt-0.5 ${
                  netPnl == null ? 'text-fg3' : netPnl > 0 ? 'text-long' : 'text-short'
                }`}
              >
                {netPnl != null ? `${netPnl > 0 ? '+' : ''}${netPnl.toFixed(2)} bps` : '—'}
              </div>
            </div>
            <div className="text-right">
              <span className="text-fg3 text-[10px]">Latency (B / L)</span>
              <div className="text-fg1 text-sm font-bold mt-0.5">
                {latBybit ?? '—'} <span className="text-[9px] text-fg3">ms</span> / {latLighter ?? '—'}{' '}
                <span className="text-[9px] text-fg3">ms</span>
              </div>
            </div>
          </div>
        </div>

        {/* Execution panel */}
        <ExecutionPanel
          ref={executionPanelRef}
          symbol={activeSymbol}
          onTradeExecuted={(msg) => addToast(msg, 'success')}
        />

        {/* Spread Chart */}
        <SpreadChart symbol={activeSymbol} />
      </section>

      {/* 2. RIGHT PANEL (matches desktop side nav width) */}
      <aside className="w-full lg:w-[280px] shrink-0 bg-bg1 flex flex-col p-[24px] overflow-y-auto space-y-6 divide-y divide-bd1 lg:divide-y-0 lg:space-y-6">
        {/* Health Section */}
        <div>
          <h3 className="text-[10px] font-bold text-fg3 uppercase tracking-wider mb-3">
            System Connectivity
          </h3>
          <div className="space-y-2 font-mono text-xs">
            <div className="flex items-center justify-between bg-card/40 border border-bd1 rounded px-3 py-2">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${latBybit != null ? 'bg-long' : 'bg-short'}`} />
                <span className="text-fg2 font-sans font-medium">Bybit WebSocket</span>
              </div>
              <span className="text-fg1 font-bold">{latBybit != null ? `${latBybit}ms` : 'FAIL'}</span>
            </div>
            <div className="flex items-center justify-between bg-card/40 border border-bd1 rounded px-3 py-2">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${latLighter != null ? 'bg-long' : 'bg-short'}`} />
                <span className="text-fg2 font-sans font-medium">Lighter Exchange API</span>
              </div>
              <span className="text-info font-bold">{latLighter != null ? `${latLighter}ms` : 'FAIL'}</span>
            </div>
          </div>
        </div>

        {/* Funding Rates Section */}
        <div className="hidden lg:block pt-5 lg:pt-0">
          <h3 className="text-[10px] font-bold text-fg3 uppercase tracking-wider mb-3">
            Funding Arb Edge
          </h3>
          <div className="bg-card/30 border border-bd1 rounded-lg p-3 space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-fg2 font-sans font-medium">Countdown (Bybit)</span>
              <span className="font-mono font-bold text-fg1">
                {countdownMin != null ? `${Math.floor(countdownMin / 60)}h ${countdownMin % 60}m` : '—'}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="bg-card border border-bd1 p-2 rounded">
                <span className="text-fg3 text-[9px] uppercase font-bold">Bybit (APR)</span>
                <div
                  className={`text-sm font-bold mt-0.5 ${
                    bybitAnnualized != null && bybitAnnualized > 0 ? 'text-long' : 'text-fg1'
                  }`}
                >
                  {bybitAnnualized != null ? `${(bybitAnnualized * 100).toFixed(2)}%` : '—'}
                </div>
              </div>
              <div className="bg-card border border-bd1 p-2 rounded">
                <span className="text-fg3 text-[9px] uppercase font-bold">Lighter (APR)</span>
                <div
                  className={`text-sm font-bold mt-0.5 ${
                    lighterAnnualized != null && lighterAnnualized > 0 ? 'text-long' : 'text-info'
                  }`}
                >
                  {lighterAnnualized != null ? `${(lighterAnnualized * 100).toFixed(2)}%` : '—'}
                </div>
              </div>
            </div>

            {netFundingAnnualized != null && (
              <div className="flex items-center justify-between text-xs border-t border-bd1/50 pt-2 font-mono">
                <span className="text-fg3 font-sans font-medium">Net Edge / APR</span>
                <span
                  className={`font-black ${
                    netFundingAnnualized > 0 ? 'text-long' : 'text-short'
                  }`}
                >
                  {netFundingAnnualized > 0 ? '+' : ''}
                  {(netFundingAnnualized * 100).toFixed(2)}%
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Activity / Alert Log Section */}
        <div className="hidden lg:flex pt-5 lg:pt-0 flex-1 flex-col min-h-[160px]">
          <div className="flex items-center justify-between mb-2.5">
            <h3 className="text-[10px] font-bold text-fg3 uppercase tracking-wider">
              System Operations Log
            </h3>
            <button
              onClick={() => setClearedAt(Date.now())}
              className="text-[9px] font-bold text-fg3 hover:text-fg1 uppercase tracking-wider px-2 py-1 bg-card/50 hover:bg-card border border-bd1 rounded transition-colors"
            >
              Clear
            </button>
          </div>
          <div className="flex-1 bg-card/20 border border-bd1 rounded-lg p-3 font-mono text-[10px] overflow-y-auto space-y-2 max-h-[220px] lg:max-h-none">
            {alertsData && Array.isArray(alertsData) && alertsData.filter(a => !clearedAt || a.ts > clearedAt).length > 0 ? (
              alertsData
                .filter(a => !clearedAt || a.ts > clearedAt)
                .slice(0, 15)
                .map((a: Alert) => (
                <div
                  key={a.id ?? a.ts}
                  className="flex flex-col items-center leading-relaxed text-fg2 border-b border-bd1/20 pb-2 text-center space-y-1"
                >
                  <div className="flex items-center justify-center gap-1.5 w-full">
                    <span className="text-fg3 font-bold shrink-0">
                      {new Date(a.ts).toLocaleTimeString(undefined, {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        hour12: false,
                      })}
                    </span>
                    <span
                      className={`shrink-0 font-bold ${
                        a.severity === 'critical'
                          ? 'text-short'
                          : a.severity === 'warning'
                          ? 'text-warn'
                          : 'text-info'
                      }`}
                    >
                      [{a.severity.toUpperCase()}]
                    </span>
                  </div>
                  <span className="text-fg1 break-all" dangerouslySetInnerHTML={{ __html: a.message }} />
                </div>
              ))
            ) : (
              <div className="text-fg3 text-center py-4">LOG STREAM EMPTY</div>
            )}
          </div>
        </div>
      </aside>

      {/* Institutional Toasts bottom right */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="bg-card border border-bd2 text-fg1 px-4 py-3 rounded-lg shadow-2xl flex items-center gap-3 animate-[slide-up_180ms_ease-out_forwards] max-w-sm transition-all duration-150 hover:border-warn/50"
          >
            <div className="w-1.5 h-1.5 rounded-full bg-long animate-pulse-fast" />
            <div className="font-mono text-xs font-semibold tracking-tight">{toast.message}</div>
          </div>
        ))}
      </div>
    </div>
  );
});
