// file: frontend/src/components/overview/SpreadChart.tsx
import React, { useState, useMemo, useEffect } from 'react';
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
  { label: '1h', minutes: 60, isDefault: false },
  { label: '4h', minutes: 240, isDefault: true },
  { label: '24h', minutes: 1440, isDefault: false },
  { label: '7d', minutes: 10080, isDefault: false },
] as const;

type TimeRange = (typeof TIME_RANGES)[number];

const MAX_CHART_POINTS = 1000;
const LINE_KEYS = ['mid_spread', 'long_spread', 'short_spread'] as const;

const CHART_MARGIN = { top: 10, right: 10, bottom: 5, left: 0 };
const AXIS_TICK = { fill: '#8c8c94', fontSize: 9, fontFamily: 'Geist Mono' };
const Y_DOMAIN: [string, string] = ['auto', 'auto'];
const MOBILE_QUERY = '(max-width: 639px)';

const TOOLTIP_CONTENT_STYLE = {
  backgroundColor: '#111113',
  border: '1px solid #2a2a2f',
  borderRadius: 6,
  fontSize: 11,
  fontFamily: 'Geist Mono',
  color: '#ededed',
  boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
};

export const SpreadChart = React.memo(function SpreadChart({ symbol }: Props) {
  const [selectedRange, setSelectedRange] = useState<TimeRange>(TIME_RANGES[1]); // default 4h
  const [hiddenLines, setHiddenLines] = useState<Set<string>>(new Set());
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(MOBILE_QUERY).matches : false
  );

  useEffect(() => {
    const media = window.matchMedia(MOBILE_QUERY);
    const updateIsMobile = () => setIsMobile(media.matches);

    updateIsMobile();
    media.addEventListener('change', updateIsMobile);
    return () => media.removeEventListener('change', updateIsMobile);
  }, []);

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
    queryKey: ['spreads', symbol, selectedRange.label],
    queryFn: () => api.spreads(symbol, { minutes: selectedRange.minutes }),
    refetchInterval: 8000,
    staleTime: 6000,
    placeholderData: keepPreviousData,
  });

  const history = data?.history ?? [];
  const count = data?.count ?? history.length;
  const stats = data?.stats as
    | { p10: number | null; p90: number | null; mean: number | null; n: number }
    | undefined;

  // Convert percentile stats to bps
  const p10Bps = stats?.p10 != null ? +(stats.p10 * 10000).toFixed(2) : null;
  const p90Bps = stats?.p90 != null ? +(stats.p90 * 10000).toFixed(2) : null;
  const meanBps = stats?.mean != null ? +(stats.mean * 10000).toFixed(2) : null;
  const showPercentiles = p10Bps != null && p90Bps != null;

  // Transform and downsample data
  const chartData = useMemo(() => {
    let rows = history;

    if (rows.length > MAX_CHART_POINTS) {
      const step = Math.ceil(rows.length / MAX_CHART_POINTS);
      rows = rows.filter((_: SpreadRow, i: number) => i % step === 0);
    }

    const showDate = selectedRange.minutes >= 1440;

    return rows.map((row: SpreadRow): ChartPoint => {
      const d = new Date(row.ts);
      const time = showDate
        ? `${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}`
        : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
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
    <div className="space-y-3.5">
      {/* Header and timeframe control */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-border-subtle/50 pb-2">
        <h3 className="text-[10px] font-bold text-text-dim uppercase tracking-wider">
          Market Spreads History (bps)
        </h3>
        <div className="flex items-center gap-2">
          {/* Timeframe selector */}
          <div className="flex bg-brand-panel border border-border-subtle rounded-md p-0.5 gap-0.5">
            {TIME_RANGES.map((range) => {
              const isActive = selectedRange.label === range.label;
              return (
                <button
                  key={range.label}
                  onClick={() => setSelectedRange(range)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-colors select-none ${
                    isActive
                      ? 'bg-accent-amber/15 border border-accent-amber/30 text-accent-amber'
                      : 'border border-transparent text-text-secondary hover:text-text-primary hover:bg-brand-base/30'
                  }`}
                >
                  {range.label}
                  {range.isDefault && <span className="text-[9px] text-accent-amber ml-0.5">★</span>}
                </button>
              );
            })}
          </div>

          {/* CSV export */}
          <button
            onClick={handleExportCsv}
            className="px-2.5 py-1 rounded text-[10px] font-mono font-bold bg-accent-cyan/10 border border-accent-cyan/30 text-accent-cyan btn-glow-cyan flex items-center gap-1 select-none"
            title="Download spreads history as CSV"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-3 w-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            CSV
          </button>
        </div>
      </div>

      {/* Percentiles indicators */}
      {showPercentiles && (
        <div className="flex items-center gap-3 text-[10px] font-mono font-bold text-text-secondary bg-brand-panel/30 border border-border-subtle/50 px-3 py-1.5 rounded-md flex-wrap">
          <div className="flex items-center gap-1">
            <span className="text-text-dim uppercase">P10:</span>
            <span className="text-accent-indigo">{p10Bps} bps</span>
          </div>
          <span className="text-border-strong">|</span>
          <div className="flex items-center gap-1">
            <span className="text-text-dim uppercase">Mean:</span>
            <span className="text-accent-amber">{meanBps} bps</span>
          </div>
          <span className="text-border-strong">|</span>
          <div className="flex items-center gap-1">
            <span className="text-text-dim uppercase">P90:</span>
            <span className="text-accent-cyan">{p90Bps} bps</span>
          </div>
          <span className="text-border-strong">|</span>
          <div className="text-text-dim text-[9px] ml-auto">{stats!.n} SAMPLES RECORDED</div>
        </div>
      )}

      {/* Chart Canvas */}
      <div className="h-56 sm:h-64 bg-brand-panel border border-border-subtle rounded-lg p-3">
        {chartData.length < 2 ? (
          <div className="h-full flex items-center justify-center text-text-dim font-mono text-xs">
            {isLoading ? 'LOADING CHART DATA...' : `ACCUMULATING TICK STREAM (${chartData.length} pts)`}
          </div>
        ) : (
          <div className="h-full w-full relative">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={CHART_MARGIN}>
                <XAxis
                  dataKey="time"
                  tick={AXIS_TICK}
                  stroke="#1f1f23"
                  dy={5}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={48}
                />
                <YAxis
                  tick={AXIS_TICK}
                  domain={Y_DOMAIN}
                  stroke="#1f1f23"
                  dx={-5}
                  tickLine={false}
                  axisLine={false}
                  width={40}
                />
                <Tooltip
                  contentStyle={TOOLTIP_CONTENT_STYLE}
                  itemStyle={{ padding: '2px 0' }}
                  cursor={{ stroke: '#2a2a2f', strokeDasharray: '3 3' }}
                />
                {!isMobile && (
                  <Legend
                    wrapperStyle={{
                      fontSize: 9,
                      fontFamily: 'Geist Mono',
                      fontWeight: 'bold',
                      paddingTop: 8,
                      cursor: 'pointer',
                    }}
                    onClick={(e: any) => {
                      if (e?.dataKey && typeof e.dataKey === 'string') toggleLine(e.dataKey);
                    }}
                    formatter={(value: string, entry: any) => {
                      const key = typeof entry.dataKey === 'string' ? entry.dataKey : '';
                      const isHidden = hiddenLines.has(key);
                      return (
                        <span
                          style={{
                            color: isHidden ? '#4a4a54' : entry.color,
                            textDecoration: isHidden ? 'line-through' : 'none',
                            paddingLeft: 4,
                            paddingRight: 12,
                          }}
                        >
                          {value}
                        </span>
                      );
                    }}
                  />
                )}
                <ReferenceLine y={0} stroke="#2a2a2f" strokeDasharray="3 3" />
                <Line
                  type="monotone"
                  dataKey="mid_spread"
                  stroke="#f5a623"
                  strokeWidth={1.8}
                  dot={false}
                  name="Mid Spread"
                  isAnimationActive={false}
                  hide={!isMobile && hiddenLines.has('mid_spread')}
                />
                {!isMobile && (
                  <>
                    <Line
                      type="monotone"
                      dataKey="long_spread"
                      stroke="#6366f1"
                      strokeWidth={1.2}
                      dot={false}
                      name="Long Spread"
                      isAnimationActive={false}
                      hide={hiddenLines.has('long_spread')}
                    />
                    <Line
                      type="monotone"
                      dataKey="short_spread"
                      stroke="#00d4ff"
                      strokeWidth={1.2}
                      dot={false}
                      name="Short Spread"
                      isAnimationActive={false}
                      hide={hiddenLines.has('short_spread')}
                    />
                  </>
                )}
                {/* Percentile guide lines */}
                {showPercentiles && !isMobile && (
                  <ReferenceLine
                    y={p10Bps!}
                    stroke="#6366f1"
                    strokeDasharray="4 4"
                    strokeWidth={0.8}
                    opacity={0.4}
                  />
                )}
                {showPercentiles && !isMobile && (
                  <ReferenceLine
                    y={p90Bps!}
                    stroke="#00d4ff"
                    strokeDasharray="4 4"
                    strokeWidth={0.8}
                    opacity={0.4}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
            <div className="absolute top-1 right-2 text-[9px] font-mono text-text-dim select-none">
              {count} POINTS DOWNSAMPLED
            </div>
          </div>
        )}
      </div>
    </div>
  );
});
