import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';
import type { TradeRecord } from '../../types/api';

const FALLBACK_SYMBOLS = ['XAUTUSDT'];

function fmtNum(value: number | null | undefined, digits = 4) {
  if (value == null || Number.isNaN(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function fmtTime(ts: number) {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function statusClass(status: string) {
  if (status === 'success') return 'border-long/30 bg-long/10 text-long';
  if (status === 'partial' || status === 'reversed') return 'border-warn/30 bg-warn/10 text-warn';
  return 'border-short/30 bg-short/10 text-short';
}

export const TradesPage = React.memo(function TradesPage() {
  const [symbol, setSymbol] = useState('');

  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: api.config,
    staleTime: 60000,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['trades', symbol],
    queryFn: () => api.trades(symbol || undefined, 100),
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const trades = useMemo(() => (Array.isArray(data) ? data as TradeRecord[] : []), [data]);
  const symbols = Array.isArray(config?.symbols) && config.symbols.length > 0
    ? config.symbols
    : FALLBACK_SYMBOLS;

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase text-gray-400">Trade Journal</h2>
          <p className="mt-1 text-xs text-fg3">{trades.length} recent executions</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setSymbol('')}
            className={`h-8 rounded-md border px-3 text-xs font-semibold ${
              symbol === ''
                ? 'border-warn text-fg1'
                : 'border-bd1 text-fg2 hover:text-fg1'
            }`}
          >
            All
          </button>
          {symbols.map((s: string) => (
            <button
              key={s}
              type="button"
              onClick={() => setSymbol(s)}
              className={`h-8 rounded-md border px-3 text-xs font-semibold ${
                symbol === s
                  ? 'border-warn text-fg1'
                  : 'border-bd1 text-fg2 hover:text-fg1'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-bd1 bg-card">
        <div className="h-full overflow-auto">
          <table className="min-w-[1120px] w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 border-b border-bd1 bg-card text-[10px] uppercase tracking-wide text-fg3">
              <tr>
                <th className="px-3 py-2 font-semibold">Time</th>
                <th className="px-3 py-2 font-semibold">Symbol</th>
                <th className="px-3 py-2 font-semibold">Strategy</th>
                <th className="px-3 py-2 font-semibold">Side</th>
                <th className="px-3 py-2 text-right font-semibold">Qty</th>
                <th className="px-3 py-2 text-right font-semibold">Bybit</th>
                <th className="px-3 py-2 text-right font-semibold">Lighter</th>
                <th className="px-3 py-2 text-right font-semibold">Fees</th>
                <th className="px-3 py-2 text-right font-semibold">Spread</th>
                <th className="px-3 py-2 text-right font-semibold">PnL</th>
                <th className="px-3 py-2 font-semibold">Status</th>
                <th className="px-3 py-2 font-semibold">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-bd1">
              {isLoading && (
                <tr>
                  <td colSpan={12} className="px-3 py-10 text-center font-mono text-fg3">
                    LOADING TRADES...
                  </td>
                </tr>
              )}
              {!isLoading && error && (
                <tr>
                  <td colSpan={12} className="px-3 py-10 text-center font-mono text-short">
                    FAILED TO LOAD TRADES
                  </td>
                </tr>
              )}
              {!isLoading && !error && trades.length === 0 && (
                <tr>
                  <td colSpan={12} className="px-3 py-10 text-center font-mono text-fg3">
                    NO TRADES RECORDED
                  </td>
                </tr>
              )}
              {!isLoading && !error && trades.map((trade) => (
                <tr key={trade.id} className="hover:bg-bg1/40">
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-fg2">{fmtTime(trade.ts)}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-fg1">{trade.symbol}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-fg2">{trade.strategy}</td>
                  <td className="max-w-[190px] truncate px-3 py-2 font-mono text-fg2">{trade.side}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right font-mono">
                    {fmtNum(trade.qty_filled, 6)} / {fmtNum(trade.qty_requested, 6)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right font-mono">
                    {trade.bybit_side} @ {fmtNum(trade.bybit_fill_price, 3)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right font-mono">
                    {fmtNum(trade.lighter_fill_price, 3)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right font-mono">
                    {fmtNum((trade.bybit_fee ?? 0) + (trade.lighter_fee ?? 0), 5)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right font-mono">
                    {fmtNum(trade.spread_bps_at_entry, 2)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right font-mono">
                    {fmtNum(trade.net_pnl_usd, 4)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">
                    <span className={`inline-flex rounded-md border px-2 py-0.5 font-mono text-[10px] uppercase ${statusClass(trade.status)}`}>
                      {trade.status}
                    </span>
                  </td>
                  <td className="max-w-[260px] truncate px-3 py-2 text-fg3" title={trade.detail ?? ''}>
                    {trade.detail ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
});
