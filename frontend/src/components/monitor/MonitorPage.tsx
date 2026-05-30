import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, type MonitorHistoryBucket, type MonitorTimeframe } from '../../services/api';
import { PairCard } from './PairCard';
import { SpreadModeToggle, SpreadMode } from './SpreadModeToggle';
import { PairSelector } from './PairSelector';
import { TimeframeToggle } from './TimeframeToggle';
import { CurrentPriceBoard, type CurrentPrice } from './CurrentPriceBoard';
import type { ChartDataPoint } from './SpreadMiniChart';

type PairHistory = Record<string, ChartDataPoint[]>;
type PricePayload = {
  bid: number;
  ask: number;
  mid: number;
};

type RawMonitorPair = {
  id: string;
  exchange_a: string;
  symbol_a: string;
  price_a?: PricePayload;
  exchange_b: string;
  symbol_b: string;
  price_b?: PricePayload;
};

type DisplayPair = RawMonitorPair & {
  canonicalId: string;
  sourceId: string;
};

const MAX_HISTORY_POINTS = 300; // ~10 min at 2s poll

// UI timeframe presets. Backend still receives an aggregation bucket.
const TIMEFRAME_OPTIONS: Record<MonitorTimeframe, { minutes: number; bucket: MonitorHistoryBucket }> = {
  '4h': { minutes: 240, bucket: '1m' },
  '24h': { minutes: 1440, bucket: '5m' },
  '7d': { minutes: 10080, bucket: '1h' },
};

function toFiniteNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function getSpreadValue(pair: any, mode: SpreadMode): number {
  if (mode === 'mid') return toFiniteNumber(pair.mid_spread_bps);
  if (mode === 'net') {
    const bestNet = Math.max(
      toFiniteNumber(pair.net_buy_bps, Number.NEGATIVE_INFINITY),
      toFiniteNumber(pair.net_sell_bps, Number.NEGATIVE_INFINITY),
    );
    return Number.isFinite(bestNet)
      ? bestNet
      : toFiniteNumber(pair.best_spread_bps ?? pair.executable_spread_bps ?? pair.sell_spread_bps);
  }
  return toFiniteNumber(pair.best_spread_bps ?? pair.executable_spread_bps ?? pair.sell_spread_bps);
}

function endpointKey(exchange: string, symbol: string): string {
  return `${exchange.toLowerCase()}:${symbol.toUpperCase()}`;
}

function canonicalPairId(pair: RawMonitorPair): string {
  return [endpointKey(pair.exchange_a, pair.symbol_a), endpointKey(pair.exchange_b, pair.symbol_b)]
    .sort()
    .join('|');
}

function collapseDirectionalPairs(pairs: RawMonitorPair[], mode: SpreadMode): DisplayPair[] {
  const byCanonicalId = new Map<string, RawMonitorPair>();

  for (const pair of pairs) {
    const canonicalId = canonicalPairId(pair);
    const current = byCanonicalId.get(canonicalId);
    if (!current || getSpreadValue(pair, mode) > getSpreadValue(current, mode)) {
      byCanonicalId.set(canonicalId, pair);
    }
  }

  return Array.from(byCanonicalId.entries()).map(([canonicalId, pair]) => ({
    ...pair,
    canonicalId,
    sourceId: pair.id,
  }));
}

const VENUE_ORDER: Record<string, number> = {
  lighter: 0,
  bybit: 1,
  binance: 2,
  mexc: 3,
  aster: 4,
  hyperliquid: 5,
  okx: 6,
  grvt: 7,
};

function collectCurrentPrices(pairs: RawMonitorPair[]): CurrentPrice[] {
  const prices = new Map<string, CurrentPrice>();

  for (const pair of pairs) {
    const endpoints = [
      { exchange: pair.exchange_a, symbol: pair.symbol_a, price: pair.price_a },
      { exchange: pair.exchange_b, symbol: pair.symbol_b, price: pair.price_b },
    ];

    for (const endpoint of endpoints) {
      if (!endpoint.price) continue;
      const key = endpointKey(endpoint.exchange, endpoint.symbol);
      if (prices.has(key)) continue;
      prices.set(key, {
        id: key,
        exchange: endpoint.exchange,
        symbol: endpoint.symbol,
        bid: endpoint.price.bid,
        ask: endpoint.price.ask,
        mid: endpoint.price.mid,
      });
    }
  }

  return Array.from(prices.values()).sort((a, b) => {
    const venueDelta = (VENUE_ORDER[a.exchange] ?? 99) - (VENUE_ORDER[b.exchange] ?? 99);
    if (venueDelta !== 0) return venueDelta;
    return a.symbol.localeCompare(b.symbol);
  });
}

export function MonitorPage() {
  const [mode, setMode] = useState<SpreadMode>('executable');
  const [timeframe, setTimeframe] = useState<MonitorTimeframe>('4h');
  const [selectedPairs, setSelectedPairs] = useState<string[]>([]);
  const historyRef = useRef<PairHistory>({});
  const availablePairIdsRef = useRef<string[]>([]);

  const { data: spreadsData } = useQuery({
    queryKey: ['monitorSpreads'],
    queryFn: () => api.monitorSpreads('gold'),
    refetchInterval: 2000,
  });

  const pairs = (spreadsData?.pairs ?? []) as RawMonitorPair[];
  const currentPrices = useMemo(() => collectCurrentPrices(pairs), [pairs]);
  const uniquePairs = useMemo(() => collapseDirectionalPairs(pairs, mode), [pairs, mode]);
  const pairByCanonicalId = useMemo(
    () => new Map(uniquePairs.map((pair) => [pair.canonicalId, pair])),
    [uniquePairs],
  );
  const selectedHistoryPairs = useMemo(
    () => selectedPairs
      .map((id) => pairByCanonicalId.get(id))
      .filter((pair): pair is DisplayPair => Boolean(pair)),
    [pairByCanonicalId, selectedPairs],
  );

  // Keep a short local fallback while backend history warms up.
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

  // Auto-select all pairs on first load. If the backend adds new pairs while
  // everything was selected, include the new pairs without requiring a reload.
  useEffect(() => {
    if (uniquePairs.length === 0) return;

    const nextIds = uniquePairs.map((p) => p.canonicalId);
    const previousIds = availablePairIdsRef.current;
    availablePairIdsRef.current = nextIds;

    setSelectedPairs((current) => {
      const nextIdSet = new Set(nextIds);
      const currentSet = new Set(current);
      const kept = current.filter((id) => nextIdSet.has(id));
      const hadAllPrevious = previousIds.length === 0 || previousIds.every((id) => currentSet.has(id));

      if (kept.length === 0) return nextIds;
      if (!hadAllPrevious) return kept.length === current.length ? current : kept;

      const missing = nextIds.filter((id) => !currentSet.has(id));
      return missing.length > 0 ? [...kept, ...missing] : kept.length === current.length ? current : kept;
    });
  }, [uniquePairs]);

  // Fetch downsampled history from the backend for the selected chart range.
  const { data: backendHistory } = useQuery({
    queryKey: ['monitorHistory', timeframe, mode, selectedHistoryPairs.map((pair) => pair.sourceId).sort()],
    enabled: selectedHistoryPairs.length > 0,
    refetchInterval: 15000,
    queryFn: async () => {
      const { minutes, bucket } = TIMEFRAME_OPTIONS[timeframe];
      const results = await Promise.all(
        selectedHistoryPairs.map(async (pair) => {
          try {
            const res = await api.monitorHistory(pair.sourceId, { minutes, timeframe: bucket });
            const points: ChartDataPoint[] = (res.history ?? [])
              .map((row) => ({ ts: toFiniteNumber(row.ts), value: getSpreadValue(row, mode) }))
              .filter((p) => Number.isFinite(p.ts) && Number.isFinite(p.value));
            return [pair.sourceId, points] as const;
          } catch {
            return [pair.sourceId, [] as ChartDataPoint[]] as const;
          }
        }),
      );
      return Object.fromEntries(results) as PairHistory;
    },
  });

  const availablePairs = uniquePairs.map((p) => ({
    id: p.canonicalId,
    label: `${p.exchange_a} ↔ ${p.exchange_b}`,
    detail: `${p.symbol_a} / ${p.symbol_b}`,
  }));

  const displayedPairs = uniquePairs
    .filter((p) => selectedPairs.includes(p.canonicalId))
    .map((p) => ({
      id: p.canonicalId,
      exchangeA: p.exchange_a,
      symbolA: p.symbol_a,
      exchangeB: p.exchange_b,
      symbolB: p.symbol_b,
      currentSpreadBps: getSpreadValue(p, mode),
      history: backendHistory?.[p.sourceId]?.length
        ? backendHistory[p.sourceId]
        : historyRef.current[p.sourceId] ?? [],
    }))
    .sort((a, b) => b.currentSpreadBps - a.currentSpreadBps);

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
        <>
          <CurrentPriceBoard prices={currentPrices} />
          <div className="flex-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-min">
            {displayedPairs.map((pair: any) => (
              <PairCard key={pair.id} {...pair} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
