// file: frontend/src/components/history/HistoryPage.tsx
import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
  Brush,
} from 'recharts';
import { api } from '../../services/api';
import type { SpreadRow, ChartPoint } from '../../types/api';

const MAX_CHART_POINTS = 768;

const LINE_KEYS = ['mid_spread', 'long_spread', 'short_spread'] as const;

const CHART_MARGIN = { top: 5, right: 5, bottom: 5, left: 5 };
const AXIS_TICK = { fill: '#6b7280', fontSize: 10 };
const Y_DOMAIN: [string, string] = ['auto', 'auto'];
const TOOLTIP_CONTENT_STYLE = {
  backgroundColor: '#1f2937',
  border: '1px solid #374151',
  borderRadius: 8,
  fontSize: 12,
};
const TOOLTIP_LABEL_STYLE = { color: '#9ca3af' };
const LEGEND_WRAPPER_STYLE = { fontSize: 11, cursor: 'pointer' };

export const HistoryPage = React.memo(function HistoryPage() {
  const [symbol] = useState('XAUTUSDT');
  const [hiddenLines, setHiddenLines] = useState<Set<string>>(new Set());

  const toggleLine = (dataKey: string) => {
    setHiddenLines((prev) => {
      const next = new Set(prev);
      if (next.has(dataKey)) {
        next.delete(dataKey);
      } else {
        if (next.size < LINE_KEYS.length - 1) {
          next.add(dataKey);
        }
      }
      return next;
    });
  };

  const { data, isLoading } = useQuery({
    queryKey: ['spreads-history', symbol],
    queryFn: () => api.spreadsHistory(symbol),
    staleTime: 60000,
  });

  const history = data?.history ?? [];
  const count = data?.count ?? 0;
  const stats = data?.stats as
    | { p10: number | null; p90: number | null; mean: number | null; n: number }
    | undefined;

  const p10Bps = stats?.p10 != null ? +(stats.p10 * 10000).toFixed(2) : null;
  const p90Bps = stats?.p90 != null ? +(stats.p90 * 10000).toFixed(2) : null;
  const meanBps = stats?.mean != null ? +(stats.mean * 10000).toFixed(2) : null;
  const showPercentiles = p10Bps != null && p90Bps != null;

  const chartData = useMemo(() => {
    let rows = history;
    if (rows.length > MAX_CHART_POINTS) {
      const step = Math.ceil(rows.length / MAX_CHART_POINTS);
      rows = rows.filter((_: SpreadRow, i: number) => i % step === 0);
    }
    return rows.map((row: SpreadRow): ChartPoint & { fullTime: string } => {
      const d = new Date(row.ts);
      const label = `${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      return {
        time: label,
        fullTime: d.toLocaleString(),
        mid_spread: +(row.exchange_spread_mid * 10000).toFixed(2),
        long_spread: +(row.long_spread * 10000).toFixed(2),
        short_spread: +(row.short_spread * 10000).toFixed(2),
      };
    });
  }, [history]);

  const dateRange = useMemo(() => {
    if (history.length === 0) return null;
    const first = new Date(history[0].ts);
    const last = new Date(history[history.length - 1].ts);
    return {
      from: first.toLocaleDateString(),
      to: last.toLocaleDateString(),
      days: Math.ceil((last.getTime() - first.getTime()) / 86400000),
    };
  }, [history]);

  return (
    <section>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-400 uppercase">
            Historical Spread — {symbol} (bps)
          </h2>
          {dateRange && (
            <p className="text-xs text-gray-500 mt-1">
              {dateRange.from} — {dateRange.to} ({dateRange.days} days)
            </p>
          )}
        </div>
        <div className="text-xs text-gray-500">
          {count.toLocaleString()} total rows
        </div>
      </div>

      {/* Percentile badges */}
      {showPercentiles && (
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-sky-500/10 border border-sky-500/20">
            <span className="text-[10px] font-medium text-sky-400/70 uppercase">P10</span>
            <span className="text-xs font-semibold text-sky-300">{p10Bps}</span>
          </span>
          {meanBps != null && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/20">
              <span className="text-[10px] font-medium text-amber-400/70 uppercase">Mean</span>
              <span className="text-xs font-semibold text-amber-300">{meanBps}</span>
            </span>
          )}
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-pink-500/10 border border-pink-500/20">
            <span className="text-[10px] font-medium text-pink-400/70 uppercase">P90</span>
            <span className="text-xs font-semibold text-pink-300">{p90Bps}</span>
          </span>
          <span className="text-[10px] text-gray-600 ml-1">{stats!.n.toLocaleString()} samples</span>
        </div>
      )}

      <div className="h-[70vh] bg-gray-900 rounded-lg border border-gray-800 p-3">
        {isLoading ? (
          <div className="h-full flex items-center justify-center text-gray-500 text-sm">
            Loading historical data...
          </div>
        ) : chartData.length < 2 ? (
          <div className="h-full flex items-center justify-center text-gray-500 text-sm">
            No historical data available ({chartData.length} points)
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={CHART_MARGIN}>
              <XAxis
                dataKey="time"
                tick={AXIS_TICK}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={AXIS_TICK}
                domain={Y_DOMAIN}
                width={50}
              />
              <Tooltip
                contentStyle={TOOLTIP_CONTENT_STYLE}
                labelStyle={TOOLTIP_LABEL_STYLE}
                labelFormatter={(_, payload) => {
                  if (payload?.[0]?.payload?.fullTime) return payload[0].payload.fullTime;
                  return '';
                }}
              />
              <Legend
                wrapperStyle={LEGEND_WRAPPER_STYLE}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                onClick={(e: any) => {
                  if (e?.dataKey && typeof e.dataKey === 'string') toggleLine(e.dataKey);
                }}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                formatter={(value: string, entry: any) => {
                  const key = typeof entry.dataKey === 'string' ? entry.dataKey : '';
                  return (
                    <span style={{
                      color: hiddenLines.has(key) ? '#4b5563' : entry.color,
                      textDecoration: hiddenLines.has(key) ? 'line-through' : 'none',
                    }}>
                      {value}
                    </span>
                  );
                }}
              />
              <ReferenceLine y={0} stroke="#4b5563" strokeDasharray="3 3" />
              <Line
                type="monotone"
                dataKey="mid_spread"
                stroke="#34d399"
                strokeWidth={1.5}
                dot={false}
                name="Mid Spread"
                isAnimationActive={false}
                hide={hiddenLines.has('mid_spread')}
              />
              <Line
                type="monotone"
                dataKey="long_spread"
                stroke="#60a5fa"
                strokeWidth={1}
                dot={false}
                name="Long Spread"
                isAnimationActive={false}
                hide={hiddenLines.has('long_spread')}
              />
              <Line
                type="monotone"
                dataKey="short_spread"
                stroke="#f87171"
                strokeWidth={1}
                dot={false}
                name="Short Spread"
                isAnimationActive={false}
                hide={hiddenLines.has('short_spread')}
              />
              {showPercentiles && (
                <ReferenceLine
                  y={p10Bps!}
                  stroke="#38bdf8"
                  strokeDasharray="6 3"
                  strokeWidth={1}
                  ifOverflow="extendDomain"
                />
              )}
              {showPercentiles && (
                <ReferenceLine
                  y={p90Bps!}
                  stroke="#f472b6"
                  strokeDasharray="6 3"
                  strokeWidth={1}
                  ifOverflow="extendDomain"
                />
              )}
              <Brush
                dataKey="time"
                height={30}
                stroke="#374151"
                fill="#111827"
                tickFormatter={() => ''}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
});
