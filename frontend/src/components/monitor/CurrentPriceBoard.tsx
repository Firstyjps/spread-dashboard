import React from 'react';
import { formatNumber } from '../../lib/format';

export type CurrentPrice = {
  id: string;
  exchange: string;
  symbol: string;
  bid: number;
  ask: number;
  mid: number;
};

function venueLabel(exchange: string): string {
  if (exchange.toLowerCase() === 'mexc') return 'MEXC';
  if (exchange.toLowerCase() === 'okx') return 'OKX';
  return exchange;
}

function formatPrice(value: number): string {
  return Number.isFinite(value) ? formatNumber(value, { decimals: 2 }) : '-';
}

export function CurrentPriceBoard({ prices }: { prices: CurrentPrice[] }) {
  if (prices.length === 0) return null;

  return (
    <section className="rounded-lg border border-bd1 bg-card/70 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-fg1">Current XAU Prices</h2>
          <p className="text-xs text-fg3">Live bid / ask / mid by venue</p>
        </div>
        <span className="shrink-0 rounded-lg border border-bd1 bg-bg1 px-2 py-1 font-mono text-[11px] text-fg3">
          {prices.length} markets
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        {prices.map((price) => (
          <div key={price.id} className="min-w-0 rounded-lg border border-bd1 bg-bg1/80 px-3 py-2">
            <div className="mb-2 flex min-w-0 items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-xs font-medium capitalize text-fg1">{venueLabel(price.exchange)}</div>
                <div className="truncate font-mono text-[11px] text-fg3">{price.symbol}</div>
              </div>
              <div className="shrink-0 text-right font-mono text-sm font-semibold tabular-nums text-fg1">
                {formatPrice(price.mid)}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 font-mono text-[11px] tabular-nums">
              <div className="min-w-0">
                <div className="text-fg3">Bid</div>
                <div className="truncate text-green-500">{formatPrice(price.bid)}</div>
              </div>
              <div className="min-w-0 text-right">
                <div className="text-fg3">Ask</div>
                <div className="truncate text-red-400">{formatPrice(price.ask)}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
