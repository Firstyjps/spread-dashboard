// file: frontend/src/components/overview/SpreadChart.tsx
import React, { useState } from 'react';
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
} from 'recharts';
import { api } from '../../services/api';

interface Props {
  symbol: string;
}

const TIME_RANGES = [
  { label: '1m', minutes: 1 },
  { label: '5m', minutes: 5 },
  { label: '15m', minutes: 15 },
  { label: '1h', minutes: 60 },
  { label: 'All', minutes: undefined },
] as const;

type TimeRange = (typeof TIME_RANGES)[number];

const LINE_KEYS = ['mid_spread', 'long_spread', 'short_spread'] as const;

export function SpreadChart({ symbol }: Props) {
  const [selectedRange, setSelectedRange] = useState<TimeRange>(TIME_RANGES[1]); // default 5m
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
    queryFn: () =>
      api.spreads(symbol, selectedRange.minutes != null
        ? { minutes: selectedRange.minutes }
        : { limit: 500 }
      ),
    refetchInterval: 3000,
  });

  const history = data?.history ?? [];
  const count = data?.count ?? history.length;

  // Convert to bps for display
  const chartData = history.map((row: any) => ({
    time: new Date(row.ts).toLocaleTimeString(),
    mid_spread: +(row.exchange_spread_mid * 10000).toFixed(2),
    long_spread: +(row.long_spread * 10000).toFixed(2),
    short_spread: +(row.short_spread * 10000).toFixed(2),
  }));

  const handleExportCsv = () => {
    const minutes = selectedRange.minutes ?? 60;
    const url = api.exportCsvUrl(symbol, minutes);
    window.open(url, '_blank');
  };

  return (
    <section>
      {/* Header with controls */}
      <div className="flex items-center justify-between mb-3">
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
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
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

      <div className="h-64 bg-gray-900 rounded-lg border border-gray-800 p-3">
        {chartData.length < 2 ? (
          <div className="h-full flex items-center justify-center text-gray-500 text-sm">
            {isLoading ? 'Loading...' : `Collecting data... (${chartData.length} points)`}
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
                <XAxis
                  dataKey="time"
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  domain={['auto', 'auto']}
                  width={45}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1f2937',
                    border: '1px solid #374151',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: '#9ca3af' }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11, cursor: 'pointer' }}
                  onClick={(e: any) => {
                    if (e?.dataKey) toggleLine(e.dataKey);
                  }}
                  formatter={(value: string, entry: any) => (
                    <span style={{
                      color: hiddenLines.has(entry.dataKey) ? '#4b5563' : entry.color,
                      textDecoration: hiddenLines.has(entry.dataKey) ? 'line-through' : 'none',
                    }}>
                      {value}
                    </span>
                  )}
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
}
