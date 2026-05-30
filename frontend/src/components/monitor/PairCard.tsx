import React from 'react';
import { SpreadMiniChart, ChartDataPoint } from './SpreadMiniChart';
import { cn } from '../../lib/cn'; // Adjusted import path

export interface PairCardProps {
  id: string;
  exchangeA: string;
  symbolA: string;
  exchangeB: string;
  symbolB: string;
  currentSpreadBps: number;
  history: ChartDataPoint[];
}

export function PairCard({
  exchangeA,
  symbolA,
  exchangeB,
  symbolB,
  currentSpreadBps,
  history
}: PairCardProps) {
  const spread = Number.isFinite(Number(currentSpreadBps)) ? Number(currentSpreadBps) : 0;
  const isPositive = spread > 0;
  const isZero = spread === 0;
  const colorClass = isPositive ? 'text-green-500' : isZero ? 'text-fg3' : 'text-red-500';
  const chartColor = isPositive ? '#22c55e' : isZero ? '#888888' : '#ef4444'; 

  return (
    <div className="flex flex-col p-4 bg-card border border-bd1 rounded-lg cursor-pointer hover:bg-card/80 transition-colors overflow-hidden">
      <div className="flex justify-between items-start gap-3 mb-2 min-w-0">
        <div className="flex min-w-0 flex-col">
          <span className="font-medium text-sm text-fg1 capitalize truncate">
            {exchangeA} ↔ {exchangeB}
          </span>
          <span className="text-xs text-fg3 truncate">
            {symbolA} / {symbolB}
          </span>
        </div>
        <div className={cn("shrink-0 text-right font-mono font-medium tabular-nums", colorClass)}>
          {spread > 0 ? '+' : ''}{spread.toFixed(1)} bps
        </div>
      </div>
      <div className="mt-2 min-w-0">
        <SpreadMiniChart data={history} color={chartColor} />
      </div>
    </div>
  );
}
