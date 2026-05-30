import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';
import { PairCard, PairCardProps } from './PairCard';
import { SpreadModeToggle, SpreadMode } from './SpreadModeToggle';
import { PairSelector } from './PairSelector';

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

const AVAILABLE_PAIRS = MOCK_PAIRS.map(p => ({
  id: p.id,
  label: `${p.exchangeA} ↔ ${p.exchangeB}`
}));

export function MonitorPage() {
  const [mode, setMode] = useState<SpreadMode>('executable');
  const [selectedPairs, setSelectedPairs] = useState<string[]>(MOCK_PAIRS.map(p => p.id));

  // Connect to API (will fail if backend is not ready, we fallback to mock data)
  const { data: spreadsData } = useQuery({
    queryKey: ['monitorSpreads'],
    queryFn: () => api.monitorSpreads('gold'),
    refetchInterval: 2000,
    retry: false, // Don't retry if failing (e.g. backend not ready)
  });

  // Wire data to PairCard grid (fallback to MOCK_PAIRS if no API data)
  const pairsData = spreadsData?.pairs 
    ? spreadsData.pairs.map(p => ({
        id: p.id,
        exchangeA: p.exchange_a,
        symbolA: p.symbol_a,
        exchangeB: p.exchange_b,
        symbolB: p.symbol_b,
        currentSpreadBps: mode === 'executable' ? p.executable_spread_bps : p.mid_spread_bps,
        history: [{ ts: Date.now(), value: mode === 'executable' ? p.executable_spread_bps : p.mid_spread_bps }] // Dummy history for now since API doesn't return full history here
      }))
    : MOCK_PAIRS;

  const displayedPairs = pairsData.filter(p => selectedPairs.includes(p.id));

  return (
    <div className="flex flex-col h-full gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Monitor</h1>
        <div className="flex items-center gap-3">
          <SpreadModeToggle mode={mode} onChange={setMode} />
          <PairSelector 
            availablePairs={AVAILABLE_PAIRS} 
            selectedPairs={selectedPairs} 
            onChange={setSelectedPairs} 
          />
        </div>
      </div>
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-min">
        {displayedPairs.map((pair) => (
          <PairCard key={pair.id} {...pair} />
        ))}
      </div>
    </div>
  );
}
