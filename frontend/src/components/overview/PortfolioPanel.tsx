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

function sideColor(side: string): string {
  return side === 'LONG' ? 'text-green-400 bg-green-900/40' : 'text-red-400 bg-red-900/40';
}

function exchangeLabel(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

// ─── Component ────────────────────────────────────────────────

export const PortfolioPanel = React.memo(function PortfolioPanel() {
  const { data, isLoading, error } = useQuery<PortfolioData>({
    queryKey: ['portfolio'],
    queryFn: api.portfolio,
    refetchInterval: 10000,
    staleTime: 8000,
  });

  if (isLoading) {
    return (
      <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-4">
        <div className="animate-pulse text-gray-500 text-sm">Loading portfolio...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-4">
        <div className="text-red-400 text-sm">Portfolio unavailable</div>
      </div>
    );
  }

  const { snapshots, totals } = data;
  const allPositions = snapshots.flatMap((s) => s.positions);
  const hasPositions = allPositions.length > 0;

  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-4 space-y-4">
      {/* Header + Totals */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider">Portfolio</h3>
        {totals.unrealized_pnl != null && (
          <span className={`text-xs font-mono font-bold ${pnlColor(totals.unrealized_pnl)}`}>
            uPnL: {totals.unrealized_pnl >= 0 ? '+' : ''}{fmt(totals.unrealized_pnl)}
          </span>
        )}
      </div>

      {/* Balance Cards */}
      <div className="grid grid-cols-2 gap-3">
        {snapshots.map((snap) => {
          const usdtBal = snap.balances.find((b) => b.currency === 'USDT');
          return (
            <div key={snap.exchange} className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-gray-400">{exchangeLabel(snap.exchange)}</span>
                {snap.errors.length > 0 && (
                  <span className="text-[10px] text-red-400 bg-red-900/30 px-1.5 py-0.5 rounded">Error</span>
                )}
              </div>
              {usdtBal ? (
                <div className="space-y-1">
                  <div className="flex items-baseline justify-between">
                    <span className="text-gray-500 text-xs">Equity</span>
                    <span className="font-mono text-sm text-white font-bold">${fmt(usdtBal.total_equity)}</span>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-gray-500 text-xs">Available</span>
                    <span className="font-mono text-xs text-gray-300">${fmt(usdtBal.available)}</span>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-gray-500 text-xs">Margin</span>
                    <span className="font-mono text-xs text-gray-300">${fmt(usdtBal.used_margin)}</span>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-gray-500 text-xs">uPnL</span>
                    <span className={`font-mono text-xs font-bold ${pnlColor(usdtBal.unrealized_pnl)}`}>
                      {usdtBal.unrealized_pnl != null && usdtBal.unrealized_pnl >= 0 ? '+' : ''}
                      ${fmt(usdtBal.unrealized_pnl)}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="text-gray-600 text-xs">No data</div>
              )}
            </div>
          );
        })}
      </div>

      {/* Combined Total Bar */}
      {totals.total_equity != null && (
        <div className="flex items-center justify-between bg-gray-800/30 rounded px-3 py-2 text-xs font-mono">
          <span className="text-gray-500">Combined Equity</span>
          <span className="text-white font-bold">${fmt(totals.total_equity)}</span>
        </div>
      )}

      {/* Positions Table */}
      {hasPositions && (
        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wider">Open Positions</label>
          <div className="mt-1.5 overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-gray-600 border-b border-gray-800">
                  <th className="text-left py-1.5 pr-2">Symbol</th>
                  <th className="text-left py-1.5 pr-2">Exchange</th>
                  <th className="text-left py-1.5 pr-2">Side</th>
                  <th className="text-right py-1.5 pr-2">Qty</th>
                  <th className="text-right py-1.5 pr-2">Entry</th>
                  <th className="text-right py-1.5 pr-2">Mark</th>
                  <th className="text-right py-1.5">uPnL</th>
                </tr>
              </thead>
              <tbody>
                {allPositions.map((pos, i) => (
                  <tr key={`${pos.exchange}-${pos.symbol}-${i}`} className="border-b border-gray-800/50">
                    <td className="py-1.5 pr-2 text-gray-300">{pos.symbol.replace('USDT', '')}</td>
                    <td className="py-1.5 pr-2 text-gray-500">{exchangeLabel(pos.exchange)}</td>
                    <td className="py-1.5 pr-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${sideColor(pos.side)}`}>
                        {pos.side}
                      </span>
                    </td>
                    <td className="py-1.5 pr-2 text-right text-gray-300">{fmt(pos.qty, 3)}</td>
                    <td className="py-1.5 pr-2 text-right text-gray-400">{fmt(pos.entry_price, 3)}</td>
                    <td className="py-1.5 pr-2 text-right text-gray-400">{fmt(pos.mark_price, 3)}</td>
                    <td className={`py-1.5 text-right font-bold ${pnlColor(pos.unrealized_pnl)}`}>
                      {pos.unrealized_pnl != null && pos.unrealized_pnl >= 0 ? '+' : ''}
                      {fmt(pos.unrealized_pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
});
