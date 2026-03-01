// file: frontend/src/components/overview/OverviewPage.tsx
import React, { useState, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';
import { SpreadChart } from './SpreadChart';

interface Props {
  data: any;
}

const STORAGE_KEY = 'spread-dashboard-visible-symbols';

function loadVisibleSymbols(): Set<string> | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return new Set(JSON.parse(stored));
  } catch {}
  return null;
}

function saveVisibleSymbols(symbols: Set<string>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...symbols]));
}

export function OverviewPage({ data }: Props) {
  const { data: fundingData } = useQuery({
    queryKey: ['funding'],
    queryFn: api.funding,
    refetchInterval: 30000,
  });
  const { data: alertsData } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => api.alerts(10),
    refetchInterval: 5000,
  });

  // All symbols from data
  const allSymbols = useMemo(() => (data ? Object.keys(data) : []), [data]);

  // Visible symbols (persisted in localStorage)
  const [visibleSymbols, setVisibleSymbols] = useState<Set<string>>(() => {
    const stored = loadVisibleSymbols();
    return stored ?? new Set(allSymbols);
  });

  // When new symbols appear (e.g., first load), auto-add them if no stored preference
  useEffect(() => {
    if (allSymbols.length > 0 && visibleSymbols.size === 0) {
      const stored = loadVisibleSymbols();
      if (!stored) {
        setVisibleSymbols(new Set(allSymbols));
      }
    }
  }, [allSymbols]);

  const toggleSymbol = (sym: string) => {
    setVisibleSymbols((prev) => {
      const next = new Set(prev);
      if (next.has(sym)) {
        next.delete(sym);
      } else {
        next.add(sym);
      }
      saveVisibleSymbols(next);
      return next;
    });
  };

  const selectAll = () => {
    const next = new Set(allSymbols);
    setVisibleSymbols(next);
    saveVisibleSymbols(next);
  };

  const selectNone = () => {
    const next = new Set<string>();
    setVisibleSymbols(next);
    saveVisibleSymbols(next);
  };

  // Filtered symbols
  const filteredSymbols = allSymbols.filter((s) => visibleSymbols.has(s));

  if (!data) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <div className="text-center">
          <div className="animate-pulse text-2xl mb-2">⏳</div>
          Waiting for price data...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Symbol Selector */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-gray-400 uppercase">Symbols</h2>
          <div className="flex gap-2 text-xs">
            <button
              onClick={selectAll}
              className="text-emerald-400 hover:text-emerald-300 transition-colors"
            >
              All
            </button>
            <span className="text-gray-600">|</span>
            <button
              onClick={selectNone}
              className="text-gray-400 hover:text-gray-300 transition-colors"
            >
              None
            </button>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {allSymbols.map((sym) => {
            const isActive = visibleSymbols.has(sym);
            const d = data[sym];
            const spread = d?.spread;
            const spreadVal = spread ? spread.exchange_spread_mid * 10000 : null;

            return (
              <button
                key={sym}
                onClick={() => toggleSymbol(sym)}
                className={`
                  px-3 py-1.5 rounded-md text-xs font-mono font-medium
                  transition-all duration-150 border
                  ${isActive
                    ? 'bg-gray-800 border-emerald-500/50 text-white'
                    : 'bg-gray-900/50 border-gray-800 text-gray-600 hover:text-gray-400 hover:border-gray-700'
                  }
                `}
              >
                <span>{sym.replace('USDT', '')}</span>
                {isActive && spreadVal != null && (
                  <span className={`ml-1.5 ${spreadVal >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {spreadVal >= 0 ? '+' : ''}{spreadVal.toFixed(1)}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <div className="text-xs text-gray-600 mt-1.5">
          {filteredSymbols.length}/{allSymbols.length} selected
        </div>
      </section>

      {/* Price Cards */}
      {filteredSymbols.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase mb-3">Prices & Spreads</h2>
          <div className="grid grid-cols-1 gap-4">
            {filteredSymbols.map((sym) => {
              const d = data[sym];
              const spread = d?.spread;
              const spreadBps = spread ? (spread.exchange_spread_mid * 10000).toFixed(2) : '-';
              const longBps = spread ? (spread.long_spread * 10000).toFixed(2) : '-';
              const shortBps = spread ? (spread.short_spread * 10000).toFixed(2) : '-';
              const zs = d?.zscore != null ? d.zscore.toFixed(2) : '-';
              const baBybit = spread ? (spread.bid_ask_spread_bybit * 10000).toFixed(2) : '-';
              const baLighter = spread ? (spread.bid_ask_spread_lighter * 10000).toFixed(2) : '-';
              const basisBps = spread?.basis_bybit_bps != null ? spread.basis_bybit_bps.toFixed(2) : '-';
              const latBybit = d?.latency_bybit != null ? Math.round(d.latency_bybit) : null;
              const latLighter = d?.latency_lighter != null ? Math.round(d.latency_lighter) : null;
              const isPositive = spread && spread.exchange_spread_mid > 0;

              return (
                <div key={sym} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                  {/* Header row */}
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-mono font-bold text-lg text-emerald-400">{sym}</span>
                    <span
                      className={`font-mono text-xl font-bold ${
                        isPositive ? 'text-green-400' : 'text-red-400'
                      }`}
                    >
                      {spreadBps} <span className="text-xs text-gray-500">bps</span>
                    </span>
                  </div>

                  {/* Price row */}
                  <div className="grid grid-cols-2 gap-4 mb-3">
                    <div>
                      <div className="text-xs text-gray-500 mb-1">Bybit Mid</div>
                      <div className="font-mono text-base">
                        {d?.bybit?.mid?.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        }) ?? '-'}
                      </div>
                      <div className="text-xs text-gray-600 font-mono">
                        B: {d?.bybit?.bid?.toLocaleString() ?? '-'} / A: {d?.bybit?.ask?.toLocaleString() ?? '-'}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">Lighter Mid</div>
                      <div className="font-mono text-base">
                        {d?.lighter?.mid?.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        }) ?? '-'}
                      </div>
                      <div className="text-xs text-gray-600 font-mono">
                        B: {d?.lighter?.bid?.toLocaleString() ?? '-'} / A: {d?.lighter?.ask?.toLocaleString() ?? '-'}
                      </div>
                    </div>
                  </div>

                  {/* Metrics row */}
                  <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-xs">
                    <div>
                      <span className="text-gray-500">Long</span>
                      <div className="font-mono text-gray-300">{longBps} bps</div>
                    </div>
                    <div>
                      <span className="text-gray-500">Short</span>
                      <div className="font-mono text-gray-300">{shortBps} bps</div>
                    </div>
                    <div>
                      <span className="text-gray-500">Z-Score</span>
                      <div className="font-mono text-gray-300">{zs}</div>
                    </div>
                    <div>
                      <span className="text-gray-500">Basis</span>
                      <div className="font-mono text-gray-300">{basisBps} bps</div>
                    </div>
                    <div>
                      <span className="text-gray-500">BA Spread</span>
                      <div className="font-mono text-gray-300">
                        B:{baBybit} / L:{baLighter}
                      </div>
                    </div>
                    <div>
                      <span className="text-gray-500">Latency</span>
                      <div className="font-mono text-gray-300">
                        {latBybit != null ? `B:${latBybit}` : 'B:-'}
                        {' / '}
                        {latLighter != null ? `L:${latLighter}` : 'L:-'}
                        <span className="text-gray-600"> ms</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Spread Charts for each visible symbol */}
      {filteredSymbols.map((sym) => (
        <SpreadChart key={sym} symbol={sym} />
      ))}

      {/* Funding Table — only visible symbols */}
      {fundingData && filteredSymbols.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase mb-3">Funding Rates</h2>
          <div className="grid grid-cols-1 gap-3">
            {filteredSymbols
              .filter((sym) => fundingData[sym])
              .map((sym) => {
                const fd = fundingData[sym];
                return (
                  <div key={sym} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono font-semibold text-emerald-400">{sym}</span>
                      {fd?.funding_diff != null && (
                        <span className={`font-mono text-sm ${fd.funding_diff > 0 ? 'text-yellow-400' : 'text-blue-400'}`}>
                          Diff: {(fd.funding_diff * 100).toFixed(4)}%
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-gray-500 text-xs">Bybit (8h)</span>
                        <div className="font-mono">
                          {fd?.bybit?.funding_rate != null
                            ? (fd.bybit.funding_rate * 100).toFixed(4) + '%'
                            : '–'}
                        </div>
                        {fd?.bybit?.annualized_rate != null && (
                          <div className="text-xs text-gray-600 font-mono">
                            Ann: {(fd.bybit.annualized_rate * 100).toFixed(2)}%
                          </div>
                        )}
                      </div>
                      <div>
                        <span className="text-gray-500 text-xs">Lighter (1h)</span>
                        <div className="font-mono">
                          {fd?.lighter?.funding_rate != null
                            ? (fd.lighter.funding_rate * 100).toFixed(4) + '%'
                            : '–'}
                        </div>
                        {fd?.lighter?.annualized_rate != null && (
                          <div className="text-xs text-gray-600 font-mono">
                            Ann: {(fd.lighter.annualized_rate * 100).toFixed(2)}%
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
          </div>
        </section>
      )}

      {/* Alerts */}
      {alertsData && Array.isArray(alertsData) && alertsData.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase mb-3">Recent Alerts</h2>
          <div className="space-y-1">
            {alertsData.slice(0, 5).map((a: any, i: number) => (
              <div
                key={i}
                className={`px-3 py-2 rounded text-sm ${
                  a.severity === 'critical'
                    ? 'bg-red-900/30 text-red-300'
                    : a.severity === 'warning'
                    ? 'bg-yellow-900/30 text-yellow-300'
                    : 'bg-gray-800 text-gray-300'
                }`}
              >
                <span className="font-mono text-xs text-gray-500 mr-2">
                  {new Date(a.ts).toLocaleTimeString()}
                </span>
                {a.message}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Empty state */}
      {filteredSymbols.length === 0 && (
        <div className="flex items-center justify-center h-32 text-gray-500 text-sm">
          No symbols selected. Click on symbols above to show them.
        </div>
      )}
    </div>
  );
}
