import React, { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, type MonitorTimeframe } from '../../services/api';
import { PairCard } from './PairCard';
import { SpreadModeToggle, SpreadMode } from './SpreadModeToggle';
import { PairSelector } from './PairSelector';
import { TimeframeToggle } from './TimeframeToggle';
import type { ChartDataPoint } from './SpreadMiniChart';

type PairHistory = Record<string, ChartDataPoint[]>;

const MAX_HISTORY_POINTS = 300; // ~10 min at 2s poll

// History window (minutes) requested from the backend per timeframe.
// Capped at the endpoint max of 10080 (7 days).
const TIMEFRAME_WINDOW_MIN: Record<Exclude<MonitorTimeframe, 'raw'>, number> = {
  '1m': 180,
  '5m': 720,
  '15m': 1440,
  '1h': 10080,
  '4h': 10080,
};

function toFiniteNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function getSpreadValue(pair: any, mode: SpreadMode): number {
  if (mode === 'mid') return toFiniteNumber(pair.mid_spread_bps);
  if (mode === 'net') return toFiniteNumber(pair.net_sell_bps ?? pair.net_buy_bps);
  // executable (default): use sell_spread for Lighter-centric pairs, else best_spread
  return toFiniteNumber(pair.sell_spread_bps ?? pair.best_spread_bps ?? pair.executable_spread_bps);
}

export function MonitorPage() {
  const [mode, setMode] = useState<SpreadMode>('executable');
  const [timeframe, setTimeframe] = useState<MonitorTimeframe>('raw');
  const [selectedPairs, setSelectedPairs] = useState<string[]>([]);
  const historyRef = useRef<PairHistory>({});

  const isLive = timeframe === 'raw';

  const { data: spreadsData } = useQuery({
    queryKey: ['monitorSpreads'],
    queryFn: () => api.monitorSpreads('gold'),
    refetchInterval: 2000,
  });

  // Accumulate client-side history from each poll (used for the "Live" timeframe)
  useEffect(() => {
    if (!spreadsData?.pairs) return;
    const ts = spreadsData.ts ?? Date.now();
    for (const pair of spreadsData.pairs) {
      const value = getSpreadValue(pair, mode);
      if (!Number.isFinite(value)) continue;
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

  // Fetch downsampled history from the backend when a non-live timeframe is active.
  const { data: backendHistory } = useQuery({
    queryKey: ['monitorHistory', timeframe, mode, [...selectedPairs].sort()],
    enabled: !isLive && selectedPairs.length > 0,
    refetchInterval: 15000,
    queryFn: async () => {
      const minutes = TIMEFRAME_WINDOW_MIN[timeframe as Exclude<MonitorTimeframe, 'raw'>];
      const results = await Promise.all(
        selectedPairs.map(async (pairId) => {
          try {
            const res = await api.monitorHistory(pairId, { minutes, timeframe });
            const points: ChartDataPoint[] = (res.history ?? [])
              .map((row) => ({ ts: toFiniteNumber(row.ts), value: getSpreadValue(row, mode) }))
              .filter((p) => Number.isFinite(p.ts) && Number.isFinite(p.value));
            return [pairId, points] as const;
          } catch {
            return [pairId, [] as ChartDataPoint[]] as const;
          }
        }),
      );
      return Object.fromEntries(results) as PairHistory;
    },
  });

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
      history: isLive
        ? historyRef.current[p.id] ?? []
        : backendHistory?.[p.id] ?? [],
    }));

  return (
    <div className="flex flex-col h-full gap-4 p-4 sm:p-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold">Monitor</h1>
        <div className="flex items-center gap-3 flex-wrap">
          <SpreadModeToggle mode={mode} onChange={setMode} />
          <TimeframeToggle timeframe={timeframe} onChange={setTimeframe} />
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
