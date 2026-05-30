import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';
import { PairCard } from './PairCard';
import { SpreadModeToggle, SpreadMode } from './SpreadModeToggle';
import { PairSelector } from './PairSelector';
import type { ChartDataPoint } from './SpreadMiniChart';

type PairHistory = Record<string, ChartDataPoint[]>;

const MAX_HISTORY_POINTS = 300; // ~10 min at 2s poll

function getSpreadValue(pair: any, mode: SpreadMode): number {
  if (mode === 'mid') return pair.mid_spread_bps ?? 0;
  if (mode === 'net') return pair.net_sell_bps ?? pair.net_buy_bps ?? 0;
  // executable (default): use sell_spread for Lighter-centric pairs, else best_spread
  return pair.sell_spread_bps ?? pair.best_spread_bps ?? 0;
}

export function MonitorPage() {
  const [mode, setMode] = useState<SpreadMode>('executable');
  const [selectedPairs, setSelectedPairs] = useState<string[]>([]);
  const historyRef = useRef<PairHistory>({});

  const { data: spreadsData } = useQuery({
    queryKey: ['monitorSpreads'],
    queryFn: () => api.monitorSpreads('gold'),
    refetchInterval: 2000,
  });

  // Accumulate history from each poll
  useEffect(() => {
    if (!spreadsData?.pairs) return;
    const ts = spreadsData.ts ?? Date.now();
    for (const pair of spreadsData.pairs) {
      const value = getSpreadValue(pair, mode);
      const arr = historyRef.current[pair.id] ?? [];
      arr.push({ ts, value });
      if (arr.length > MAX_HISTORY_POINTS) arr.shift();
      historyRef.current[pair.id] = arr;
    }
  }, [spreadsData, mode]);

  // Auto-select all pairs on first load
  useEffect(() => {
    if (spreadsData?.pairs && selectedPairs.length === 0) {
      setSelectedPairs(spreadsData.pairs.map((p: any) => p.id));
    }
  }, [spreadsData]);

  const pairs = spreadsData?.pairs ?? [];
  const availablePairs = pairs.map((p: any) => ({
    id: p.id,
    label: `${p.exchange_a} ↔ ${p.exchange_b}`,
  }));

  const displayedPairs = pairs
    .filter((p: any) => selectedPairs.includes(p.id))
    .map((p: any) => ({
      id: p.id,
      exchangeA: p.exchange_a,
      symbolA: p.symbol_a,
      exchangeB: p.exchange_b,
      symbolB: p.symbol_b,
      currentSpreadBps: getSpreadValue(p, mode),
      history: historyRef.current[p.id] ?? [],
    }));

  return (
    <div className="flex flex-col h-full gap-4 p-4 sm:p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Monitor</h1>
        <div className="flex items-center gap-3">
          <SpreadModeToggle mode={mode} onChange={setMode} />
          <PairSelector
            availablePairs={availablePairs}
            selectedPairs={selectedPairs}
            onChange={setSelectedPairs}
          />
        </div>
      </div>
      {pairs.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-fg3 text-sm">
          Connecting to exchanges...
        </div>
      ) : (
        <div className="flex-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-min">
          {displayedPairs.map((pair: any) => (
            <PairCard key={pair.id} {...pair} />
          ))}
        </div>
      )}
    </div>
  );
}
