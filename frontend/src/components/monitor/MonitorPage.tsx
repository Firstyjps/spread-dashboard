import React from 'react';
import { PairCard, PairCardProps } from './PairCard';

const MOCK_PAIRS: PairCardProps[] = [
  {
    id: 'bybit:XAUTUSDT-lighter:XAU',
    exchangeA: 'Bybit',
    symbolA: 'XAUT',
    exchangeB: 'Lighter',
    symbolB: 'XAU',
    currentSpreadBps: 27.3,
    history: Array.from({ length: 20 }).map((_, i) => ({ ts: i, value: 20 + Math.random() * 10 })),
  },
  {
    id: 'bybit:XAUTUSDT-binance:XAUTUSDT',
    exchangeA: 'Bybit',
    symbolA: 'XAUT',
    exchangeB: 'Binance',
    symbolB: 'XAUT',
    currentSpreadBps: 0.8,
    history: Array.from({ length: 20 }).map((_, i) => ({ ts: i, value: -2 + Math.random() * 5 })),
  },
  {
    id: 'lighter:XAU-grvt:XAU',
    exchangeA: 'Lighter',
    symbolA: 'XAU',
    exchangeB: 'GRVT',
    symbolB: 'XAU',
    currentSpreadBps: -0.3,
    history: Array.from({ length: 20 }).map((_, i) => ({ ts: i, value: Math.random() * 2 - 1 })),
  },
];

export function MonitorPage() {
  return (
    <div className="flex flex-col h-full gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Monitor</h1>
        <div className="flex gap-2">
          {/* Controls will go here */}
        </div>
      </div>
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-min">
        {MOCK_PAIRS.map((pair) => (
          <PairCard key={pair.id} {...pair} />
        ))}
      </div>
    </div>
  );
}
