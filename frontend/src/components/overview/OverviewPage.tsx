// file: frontend/src/components/overview/OverviewPage.tsx
import React, { useState, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';
import { SpreadChart } from './SpreadChart';
import { ExecutionPanel } from './ExecutionPanel';
import type { SymbolData, SymbolDataMap, Alert } from '../../types/api';

interface Props {
  data: SymbolDataMap | null;
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

// Helper: color Z-Score by intensity
function zsColor(z: number | null | undefined): string {
  if (z == null) return 'text-gray-500';
  const abs = Math.abs(z);
  if (abs >= 2.0) return 'text-orange-400';
  if (abs >= 1.0) return 'text-yellow-400';
  return 'text-gray-400';
}

// Helper: color imbalance value
function imbColor(v: number | null | undefined): string {
  if (v == null) return 'text-gray-500';
  if (v > 0.3) return 'text-green-400';
  if (v < -0.3) return 'text-red-400';
  return 'text-gray-400';
}

// Helper: format imbalance
function fmtImb(v: number | null | undefined): string {
  if (v == null) return '-';
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}`;
}

// Helper: feed staleness dot color
function staleDot(d: SymbolData | undefined): string {
  const bybitAge = d?.bybit?.received_at ? (Date.now() - d.bybit.received_at) / 1000 : 999;
  const lighterAge = d?.lighter?.received_at ? (Date.now() - d.lighter.received_at) / 1000 : 999;
  const maxAge = Math.max(bybitAge, lighterAge);
  if (maxAge < 5) return 'bg-green-400';
  if (maxAge < 15) return 'bg-yellow-400';
  return 'bg-red-400';
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
    queryFn: () => api.alerts(10),
    refetchInterval: 15000,
    staleTime: 10000,
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
              const netPnl = d?.net_pnl_bps;
              const latBybit = d?.latency_bybit != null ? Math.round(d.latency_bybit) : null;
              const latLighter = d?.latency_lighter != null ? Math.round(d.latency_lighter) : null;
              const isPositive = spread && spread.exchange_spread_mid > 0;

              return (
                <div key={sym} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                  {/* Header row */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${staleDot(d)}`} title="Feed freshness" />
                      <span className="font-mono font-bold text-lg text-emerald-400">{sym}</span>
                    </div>
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
                  <div className="grid grid-cols-4 sm:grid-cols-8 gap-2 text-xs">
                    <div>
                      <span className="text-gray-500">Long</span>
                      <div className="font-mono text-gray-300">{longBps} bps</div>
                    </div>
                    <div>
                      <span className="text-gray-500">Short</span>
                      <div className="font-mono text-gray-300">{shortBps} bps</div>
                    </div>
                    <div className="relative group">
                      <span className="text-gray-500">Net PnL</span>
                      <div className={`font-mono cursor-help ${
                        netPnl == null ? 'text-gray-500'
                          : netPnl > 0 ? 'text-green-400'
                          : 'text-red-400'
                      }`}>
                        {netPnl != null ? `${netPnl > 0 ? '+' : ''}${netPnl.toFixed(2)} bps` : '-'}
                      </div>
                      {/* Cost breakdown tooltip */}
                      {spread && netPnl != null && (() => {
                        const grossBps = Math.max(
                          Math.abs(spread.long_spread) * 10000,
                          Math.abs(spread.short_spread) * 10000
                        );
                        return (
                          <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-10
                            bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs font-mono
                            whitespace-nowrap shadow-lg">
                            <div className="text-gray-300">Gross: {grossBps.toFixed(2)} bps</div>
                            <div className="text-red-400/70">Fees: -2.00 bps <span className="text-gray-600">(Bybit)</span></div>
                            <div className="text-red-400/70">Slip: -1.00 bps <span className="text-gray-600">(est.)</span></div>
                            <div className="border-t border-gray-700 mt-1 pt-1">
                              <span className={netPnl > 0 ? 'text-green-400' : 'text-red-400'}>
                                Net: {netPnl > 0 ? '+' : ''}{netPnl.toFixed(2)} bps
                              </span>
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                    <div>
                      <span className="text-gray-500">Z-Score</span>
                      <div className={`font-mono ${zsColor(d?.zscore)}`}>{zs}</div>
                    </div>
                    <div>
                      <span className="text-gray-500">Imbalance</span>
                      <div className="font-mono">
                        <span className={imbColor(d?.imbalance_bybit)}>B:{fmtImb(d?.imbalance_bybit)}</span>
                        {' '}
                        <span className={imbColor(d?.imbalance_lighter)}>L:{fmtImb(d?.imbalance_lighter)}</span>
                      </div>
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
                  <ExecutionPanel symbol={sym} />
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
                const bybitRate = fd?.bybit?.funding_rate;
                const lighterRate = fd?.lighter?.funding_rate;

                // Normalize to hourly rate for fair comparison
                const bybitHourly = bybitRate != null ? bybitRate / 8 : null;
                const lighterHourly = lighterRate != null ? lighterRate / 1 : null;

                // 8h projected cost (what you pay/receive per 8h funding cycle)
                const bybit8h = bybitRate;
                const lighter8h = lighterRate != null ? lighterRate * 8 : null;

                // Net funding for arb position (Long Lighter + Short Bybit)
                // Positive = you receive, Negative = you pay
                const netFunding8h = (bybit8h != null && lighter8h != null)
                  ? (bybit8h - lighter8h)  // short Bybit receives when rate positive, long Lighter pays when rate positive
                  : null;

                // Next funding countdown (Bybit)
                const nextFundingMs = fd?.bybit?.next_funding_time;
                const countdown = nextFundingMs ? Math.max(0, nextFundingMs - Date.now()) : null;
                const countdownMin = countdown != null ? Math.floor(countdown / 60000) : null;
                const countdownSec = countdown != null ? Math.floor((countdown % 60000) / 1000) : null;

                // Color helpers
                const rateColor = (r: number | null) => {
                  if (r == null) return 'text-gray-500';
                  if (r > 0.0001) return 'text-green-400';   // positive = longs pay shorts
                  if (r < -0.0001) return 'text-red-400';    // negative = shorts pay longs
                  return 'text-gray-300';
                };

                return (
                  <div key={sym} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <span className="font-mono font-semibold text-emerald-400">{sym}</span>
                        {countdownMin != null && (
                          <span className="text-xs font-mono text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                            Next: {countdownMin}m {countdownSec}s
                          </span>
                        )}
                      </div>
                      {netFunding8h != null && (
                        <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${
                          netFunding8h > 0 ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'
                        }`}>
                          Net/8h: {netFunding8h > 0 ? '+' : ''}{(netFunding8h * 100).toFixed(4)}%
                        </span>
                      )}
                    </div>

                    {/* Exchange rates side by side */}
                    <div className="grid grid-cols-2 gap-4 mb-3">
                      {/* Bybit */}
                      <div className="bg-gray-800/50 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-500 text-xs font-medium">Bybit</span>
                          <span className="text-gray-600 text-xs">8h cycle</span>
                        </div>
                        <div className={`font-mono text-lg font-bold ${rateColor(bybitRate)}`}>
                          {bybitRate != null ? `${(bybitRate * 100).toFixed(4)}%` : '–'}
                        </div>
                        <div className="grid grid-cols-2 gap-1 mt-2 text-xs font-mono">
                          <div>
                            <span className="text-gray-600">Hourly</span>
                            <div className="text-gray-400">
                              {bybitHourly != null ? `${(bybitHourly * 100).toFixed(4)}%` : '–'}
                            </div>
                          </div>
                          <div>
                            <span className="text-gray-600">Annual</span>
                            <div className="text-gray-400">
                              {fd?.bybit?.annualized_rate != null
                                ? `${(fd.bybit.annualized_rate * 100).toFixed(2)}%`
                                : '–'}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Lighter */}
                      <div className="bg-gray-800/50 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-500 text-xs font-medium">Lighter</span>
                          <span className="text-gray-600 text-xs">1h cycle</span>
                        </div>
                        <div className={`font-mono text-lg font-bold ${rateColor(lighterRate)}`}>
                          {lighterRate != null ? `${(lighterRate * 100).toFixed(4)}%` : '–'}
                        </div>
                        <div className="grid grid-cols-2 gap-1 mt-2 text-xs font-mono">
                          <div>
                            <span className="text-gray-600">Per 8h</span>
                            <div className="text-gray-400">
                              {lighter8h != null ? `${(lighter8h * 100).toFixed(4)}%` : '–'}
                            </div>
                          </div>
                          <div>
                            <span className="text-gray-600">Annual</span>
                            <div className="text-gray-400">
                              {fd?.lighter?.annualized_rate != null
                                ? `${(fd.lighter.annualized_rate * 100).toFixed(2)}%`
                                : '–'}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Summary bar */}
                    <div className="flex items-center justify-between text-xs bg-gray-800/30 rounded px-3 py-2">
                      <div className="font-mono">
                        <span className="text-gray-500">Diff (L-B): </span>
                        {fd?.funding_diff != null ? (
                          <span className={fd.funding_diff > 0 ? 'text-yellow-400' : 'text-blue-400'}>
                            {fd.funding_diff > 0 ? '+' : ''}{(fd.funding_diff * 100).toFixed(4)}%
                          </span>
                        ) : '–'}
                      </div>
                      <div className="font-mono">
                        <span className="text-gray-500">Hourly Diff: </span>
                        {bybitHourly != null && lighterHourly != null ? (
                          <span className={lighterHourly - bybitHourly > 0 ? 'text-yellow-400' : 'text-blue-400'}>
                            {(lighterHourly - bybitHourly) > 0 ? '+' : ''}{((lighterHourly - bybitHourly) * 100).toFixed(4)}%
                          </span>
                        ) : '–'}
                      </div>
                      {bybitRate != null && lighterRate != null && (
                        <div className="font-mono">
                          <span className="text-gray-500">Arb: </span>
                          <span className={netFunding8h != null && netFunding8h > 0 ? 'text-green-400' : 'text-red-400'}>
                            {netFunding8h != null && netFunding8h > 0 ? 'Favorable' : 'Costly'}
                          </span>
                        </div>
                      )}
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
            {alertsData.slice(0, 5).map((a: Alert) => (
              <div
                key={a.id ?? a.ts}
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
});
