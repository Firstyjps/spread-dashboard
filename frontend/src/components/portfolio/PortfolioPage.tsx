import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';

// ─── Types ────────────────────────────────────────────────────

interface NormalizedBalance {
  exchange: string;
  currency: string;
  total_equity: number | null;
  available: number | null;
  used_margin: number | null;
  unrealized_pnl: number | null;
}

interface NormalizedPosition {
  exchange: string;
  symbol: string;
  side: string;
  qty: number;
  entry_price: number | null;
  mark_price: number | null;
  unrealized_pnl: number | null;
  leverage: number | null;
  liq_price: number | null;
}

interface ExchangeSnapshot {
  exchange: string;
  balances: NormalizedBalance[];
  positions: NormalizedPosition[];
  errors: string[];
}

interface PortfolioData {
  snapshots: ExchangeSnapshot[];
  totals: {
    currency?: string;
    total_equity?: number;
    available?: number;
    used_margin?: number;
    unrealized_pnl?: number;
  };
}

// ─── Helpers ──────────────────────────────────────────────────

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '-';
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function pnlColor(n: number | null | undefined): string {
  if (n == null) return 'text-gray-500';
  if (n > 0) return 'text-green-400';
  if (n < 0) return 'text-red-400';
  return 'text-gray-400';
}

function pnlBg(n: number | null | undefined): string {
  if (n == null) return '';
  if (n > 0) return 'bg-green-900/20';
  if (n < 0) return 'bg-red-900/20';
  return '';
}

function sideColor(side: string): string {
  return side === 'LONG' ? 'text-green-400 bg-green-900/40' : 'text-red-400 bg-red-900/40';
}

function exchangeLabel(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

// ─── Component ────────────────────────────────────────────────

export const PortfolioPage = React.memo(function PortfolioPage() {
  const { data, isLoading, error } = useQuery<PortfolioData>({
    queryKey: ['portfolio'],
    queryFn: api.portfolio,
    refetchInterval: 10000,
    staleTime: 8000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <div className="text-center">
          <div className="animate-pulse text-2xl mb-2">Loading portfolio...</div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400">
        Portfolio unavailable
      </div>
    );
  }

  const { snapshots, totals } = data;
  const allPositions = snapshots.flatMap((s) => s.positions);

  // Group positions by symbol for paired view
  const symbolMap = new Map<string, NormalizedPosition[]>();
  for (const pos of allPositions) {
    const key = pos.symbol;
    if (!symbolMap.has(key)) symbolMap.set(key, []);
    symbolMap.get(key)!.push(pos);
  }

  return (
    <div className="space-y-6">
      {/* ── Combined Totals ── */}
      {totals.total_equity != null && (
        <div className={`rounded-lg border border-gray-800 p-5 ${pnlBg(totals.unrealized_pnl)}`}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider">Combined Portfolio</h2>
            <span className="text-xs text-gray-600 font-mono">USDT</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-gray-500 mb-1">Total Equity</div>
              <div className="font-mono text-xl font-bold text-white">${fmt(totals.total_equity)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">Available</div>
              <div className="font-mono text-xl text-gray-300">${fmt(totals.available)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">Used Margin</div>
              <div className="font-mono text-xl text-gray-300">${fmt(totals.used_margin)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">Unrealized PnL</div>
              <div className={`font-mono text-xl font-bold ${pnlColor(totals.unrealized_pnl)}`}>
                {totals.unrealized_pnl != null && totals.unrealized_pnl >= 0 ? '+' : ''}
                ${fmt(totals.unrealized_pnl)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Per-Exchange Balances ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {snapshots.map((snap) => {
          const usdtBal = snap.balances.find((b) => b.currency === 'USDT');
          const _otherBals = snap.balances.filter((b) => b.currency !== 'USDT');
          const posCount = snap.positions.length;

          return (
            <div key={snap.exchange} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-emerald-400">{exchangeLabel(snap.exchange)}</span>
                  <span className="text-xs text-gray-600">{posCount} position{posCount !== 1 ? 's' : ''}</span>
                </div>
                {snap.errors.length > 0 && (
                  <span className="text-[10px] text-red-400 bg-red-900/30 px-2 py-0.5 rounded">
                    {snap.errors.length} error{snap.errors.length > 1 ? 's' : ''}
                  </span>
                )}
              </div>

              {usdtBal ? (
                <div className="space-y-2">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-800/50 rounded p-2.5">
                      <div className="text-xs text-gray-500">Equity</div>
                      <div className="font-mono text-sm font-bold text-white">${fmt(usdtBal.total_equity)}</div>
                    </div>
                    <div className="bg-gray-800/50 rounded p-2.5">
                      <div className="text-xs text-gray-500">Available</div>
                      <div className="font-mono text-sm text-gray-300">${fmt(usdtBal.available)}</div>
                    </div>
                    <div className="bg-gray-800/50 rounded p-2.5">
                      <div className="text-xs text-gray-500">Margin Used</div>
                      <div className="font-mono text-sm text-gray-300">${fmt(usdtBal.used_margin)}</div>
                    </div>
                    <div className={`bg-gray-800/50 rounded p-2.5 ${pnlBg(usdtBal.unrealized_pnl)}`}>
                      <div className="text-xs text-gray-500">uPnL</div>
                      <div className={`font-mono text-sm font-bold ${pnlColor(usdtBal.unrealized_pnl)}`}>
                        {usdtBal.unrealized_pnl != null && usdtBal.unrealized_pnl >= 0 ? '+' : ''}
                        ${fmt(usdtBal.unrealized_pnl)}
                      </div>
                    </div>
                  </div>

                </div>
              ) : (
                <div className="text-gray-600 text-sm py-4">No balance data</div>
              )}

              {/* Errors */}
              {snap.errors.length > 0 && (
                <div className="mt-2 space-y-1">
                  {snap.errors.map((err, i) => (
                    <div key={i} className="text-xs text-red-400/70 bg-red-900/10 rounded px-2 py-1">{err}</div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Open Positions ── */}
      {allPositions.length > 0 && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-3">
            Open Positions
            <span className="ml-2 text-gray-600 font-normal">{allPositions.length}</span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-gray-800">
                  <th className="text-left py-2 pr-3">Symbol</th>
                  <th className="text-left py-2 pr-3">Exchange</th>
                  <th className="text-left py-2 pr-3">Side</th>
                  <th className="text-right py-2 pr-3">Qty</th>
                  <th className="text-right py-2 pr-3">Entry</th>
                  <th className="text-right py-2 pr-3">Mark</th>
                  <th className="text-right py-2 pr-3">Leverage</th>
                  <th className="text-right py-2 pr-3">Liq. Price</th>
                  <th className="text-right py-2">uPnL</th>
                </tr>
              </thead>
              <tbody>
                {Array.from(symbolMap.entries()).map(([symbol, positions]) => (
                  <React.Fragment key={symbol}>
                    {positions.map((pos, i) => (
                      <tr
                        key={`${pos.exchange}-${pos.symbol}-${i}`}
                        className={`border-b border-gray-800/40 hover:bg-gray-800/30 transition-colors ${
                          i === positions.length - 1 ? 'border-b-gray-700' : ''
                        }`}
                      >
                        <td className="py-2.5 pr-3 text-gray-200 font-medium">
                          {i === 0 ? symbol.replace('USDT', '') : ''}
                        </td>
                        <td className="py-2.5 pr-3 text-gray-500 text-xs">
                          {exchangeLabel(pos.exchange)}
                        </td>
                        <td className="py-2.5 pr-3">
                          <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${sideColor(pos.side)}`}>
                            {pos.side}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3 text-right text-gray-300">{fmt(pos.qty, 3)}</td>
                        <td className="py-2.5 pr-3 text-right text-gray-400">{fmt(pos.entry_price, 3)}</td>
                        <td className="py-2.5 pr-3 text-right text-gray-400">{fmt(pos.mark_price, 3)}</td>
                        <td className="py-2.5 pr-3 text-right text-gray-500">
                          {pos.leverage != null ? `${fmt(pos.leverage, 0)}x` : '-'}
                        </td>
                        <td className="py-2.5 pr-3 text-right text-yellow-500/70 text-xs">
                          {fmt(pos.liq_price, 2)}
                        </td>
                        <td className={`py-2.5 text-right font-bold ${pnlColor(pos.unrealized_pnl)}`}>
                          {pos.unrealized_pnl != null && pos.unrealized_pnl >= 0 ? '+' : ''}
                          ${fmt(pos.unrealized_pnl)}
                        </td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* Net position summary per symbol */}
          <div className="mt-4 pt-3 border-t border-gray-800">
            <div className="text-[10px] text-gray-600 uppercase mb-2">Net Exposure per Symbol</div>
            <div className="flex flex-wrap gap-3">
              {Array.from(symbolMap.entries()).map(([symbol, positions]) => {
                let net = 0;
                let totalPnl = 0;
                for (const p of positions) {
                  const signed = p.side === 'LONG' ? p.qty : -p.qty;
                  net += signed;
                  totalPnl += p.unrealized_pnl ?? 0;
                }
                const isHedged = Math.abs(net) < 0.001;
                return (
                  <div key={symbol} className="bg-gray-800/50 rounded px-3 py-2 text-xs font-mono">
                    <span className="text-gray-400">{symbol.replace('USDT', '')}</span>
                    <span className={`ml-2 font-bold ${isHedged ? 'text-cyan-400' : 'text-yellow-400'}`}>
                      {isHedged ? 'Hedged' : `Net ${net > 0 ? '+' : ''}${fmt(net, 3)}`}
                    </span>
                    <span className={`ml-2 ${pnlColor(totalPnl)}`}>
                      {totalPnl >= 0 ? '+' : ''}${fmt(totalPnl)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* No positions state */}
      {allPositions.length === 0 && (
        <div className="flex items-center justify-center h-32 bg-gray-900 rounded-lg border border-gray-800 text-gray-500 text-sm">
          No open positions
        </div>
      )}
    </div>
  );
});
