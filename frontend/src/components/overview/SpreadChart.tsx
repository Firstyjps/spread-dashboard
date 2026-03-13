// file: frontend/src/components/overview/SpreadChart.tsx
import React, { useState, useMemo } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import type { SpreadRow, ChartPoint } from '../../types/api';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from 'recharts';
import { api } from '../../services/api';

interface Props {
  symbol: string;
}

const TIME_RANGES = [
  { label: '5m', minutes: 5 },
  { label: '15m', minutes: 15 },
  { label: '1h', minutes: 60 },
  { label: '4h', minutes: 240 },
  { label: '24h', minutes: 1440 },
  { label: '7d', minutes: 10080 },
] as const;

type TimeRange = (typeof TIME_RANGES)[number];

// Max chart points — backend already downsamples to 2000, this is a safety net
const MAX_CHART_POINTS = 2000;

const LINE_KEYS = ['mid_spread', 'long_spread', 'short_spread'] as const;

// Hoisted style objects — prevents new references every render
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

export const SpreadChart = React.memo(function SpreadChart({ symbol }: Props) {
  const [selectedRange, setSelectedRange] = useState<TimeRange>(TIME_RANGES[2]); // default 1h
  const [hiddenLines, setHiddenLines] = useState<Set<string>>(new Set());

  const toggleLine = (dataKey: string) => {
    setHiddenLines((prev) => {
      const next = new Set(prev);
      if (next.has(dataKey)) {
        next.delete(dataKey);
      } else {
        // Don't allow hiding ALL lines
        if (next.size < LINE_KEYS.length - 1) {
          next.add(dataKey);
        }
      }
      return next;
    });
  };

  const { data, isLoading } = useQuery({
    queryKey: ['spreads', symbol, selectedRange.label],
    queryFn: () => api.spreads(symbol, { minutes: selectedRange.minutes }),
    refetchInterval: 10000,
    staleTime: 8000,
    placeholderData: keepPreviousData,
  });

  const history = data?.history ?? [];
  const count = data?.count ?? history.length;
  const stats = data?.stats as
    | { p10: number | null; p90: number | null; mean: number | null; n: number }
    | undefined;

  // Convert percentile stats to bps (same unit as chart Y-axis)
  const p10Bps = stats?.p10 != null ? +(stats.p10 * 10000).toFixed(2) : null;
  const p90Bps = stats?.p90 != null ? +(stats.p90 * 10000).toFixed(2) : null;
  const meanBps = stats?.mean != null ? +(stats.mean * 10000).toFixed(2) : null;
  const showPercentiles = p10Bps != null && p90Bps != null;

  // Convert to bps + downsample if too many points
  const chartData = useMemo(() => {
    let rows = history;

    // Downsample: take every Nth row to stay under MAX_CHART_POINTS
    if (rows.length > MAX_CHART_POINTS) {
      const step = Math.ceil(rows.length / MAX_CHART_POINTS);
      rows = rows.filter((_: SpreadRow, i: number) => i % step === 0);
    }

    // For ranges >= 4h, show date+time; otherwise just time
    const showDate = selectedRange.minutes >= 240;

    return rows.map((row: SpreadRow): ChartPoint => {
      const d = new Date(row.ts);
      const time = showDate
        ? `${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
        : d.toLocaleTimeString();
      return {
        time,
        mid_spread: +(row.exchange_spread_mid * 10000).toFixed(2),
        long_spread: +(row.long_spread * 10000).toFixed(2),
        short_spread: +(row.short_spread * 10000).toFixed(2),
      };
    });
  }, [history, selectedRange.minutes]);

  const handleExportCsv = () => {
    const url = api.exportCsvUrl(symbol, selectedRange.minutes);
    window.open(url, '_blank');
  };

  return (
    <section>
      {/* Header with controls */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-400 uppercase">
          Spread Chart — {symbol} (bps)
        </h2>
        <div className="flex items-center gap-2">
          {/* Time Range Buttons */}
          <div className="flex bg-gray-800 rounded-md p-0.5 gap-0.5">
            {TIME_RANGES.map((range) => (
              <button
                key={range.label}
                onClick={() => setSelectedRange(range)}
                className={`px-2 py-1.5 sm:px-2.5 sm:py-1 rounded text-xs font-medium transition-colors ${
                  selectedRange.label === range.label
                    ? 'bg-emerald-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-700'
                }`}
              >
                {range.label}
              </button>
            ))}
          </div>

          {/* CSV Export Button */}
          <button
            onClick={handleExportCsv}
            className="px-2.5 py-1 rounded text-xs font-medium bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors flex items-center gap-1"
            title="Export CSV"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            CSV
          </button>
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
          <span className="text-[10px] text-gray-600 ml-1">{stats!.n} samples</span>
        </div>
      )}

      <div className="h-48 sm:h-64 bg-gray-900 rounded-lg border border-gray-800 p-3">
        {chartData.length < 2 ? (
          <div className="h-full flex items-center justify-center text-gray-500 text-sm">
            {isLoading ? 'Loading...' : `Collecting data... (${chartData.length} points)`}
          </div>
        ) : (
          <>
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
                  width={45}
                />
                <Tooltip
                  contentStyle={TOOLTIP_CONTENT_STYLE}
                  labelStyle={TOOLTIP_LABEL_STYLE}
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
                  strokeWidth={2}
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
                {/* P10/P90 dashed lines */}
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
              </LineChart>
            </ResponsiveContainer>
            {/* Data point count */}
            <div className="text-right text-xs text-gray-600 -mt-1">
              {count} pts
            </div>
          </>
        )}
      </div>
    </section>
  );
});
