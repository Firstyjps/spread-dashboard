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
  const isPositive = currentSpreadBps > 0;
  const isZero = currentSpreadBps === 0;
  const colorClass = isPositive ? 'text-green-500' : isZero ? 'text-fg3' : 'text-red-500';
  const chartColor = isPositive ? '#22c55e' : isZero ? '#888888' : '#ef4444'; 

  return (
    <div className="flex flex-col p-4 bg-card border border-bd1 rounded-lg cursor-pointer hover:bg-card/80 transition-colors">
      <div className="flex justify-between items-start mb-2">
        <div className="flex flex-col">
          <span className="font-medium text-sm text-fg1 capitalize">
            {exchangeA} ↔ {exchangeB}
          </span>
          <span className="text-xs text-fg3">
            {symbolA} / {symbolB}
          </span>
        </div>
        <div className={cn("text-right font-mono font-medium", colorClass)}>
          {currentSpreadBps > 0 ? '+' : ''}{currentSpreadBps.toFixed(1)} bps
        </div>
      </div>
      <div className="mt-2">
        <SpreadMiniChart data={history} color={chartColor} />
      </div>
    </div>
  );
}
