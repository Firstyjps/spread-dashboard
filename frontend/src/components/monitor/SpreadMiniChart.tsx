import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AreaChart, Area, ReferenceLine, YAxis, XAxis, CartesianGrid, Tooltip } from 'recharts';

export type ChartDataPoint = {
  ts: number;
  value: number;
};

interface Props {
  data: ChartDataPoint[];
  color: string;
}

const CHART_HEIGHT = 152;

function computePercentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

function computeDomain(values: number[]): [number, number] {
  if (values.length === 0) return [-1, 1];

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  const pad = range === 0
    ? Math.max(Math.abs(max) * 0.01, 0.5)
    : Math.max(range * 0.18, 0.25);

  return [min - pad, max + pad];
}

function formatBpsTick(value: number): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  return Math.abs(number) >= 100 ? number.toFixed(0) : number.toFixed(1);
}

export function SpreadMiniChart({ data, color }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [chartWidth, setChartWidth] = useState(0);

  const chartData = useMemo(
    () => (data ?? [])
      .map((point) => ({ ts: Number(point.ts), value: Number(point.value) }))
      .filter((point) => Number.isFinite(point.ts) && Number.isFinite(point.value)),
    [data],
  );

  const { p10, p90, domain } = useMemo(() => {
    const values = chartData.map(d => d.value);
    const sorted = [...values].sort((a, b) => a - b);
    const nextP10 = computePercentile(sorted, 10);
    const nextP90 = computePercentile(sorted, 90);
    return {
      p10: nextP10,
      p90: nextP90,
      domain: computeDomain([...values, nextP10, nextP90]),
    };
  }, [chartData]);

  const formatTime = (ts: number) => {
    const d = new Date(ts);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  const gradId = `grad-${color.replace('#', '')}`;

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    const updateWidth = () => {
      const width = Math.floor(node.getBoundingClientRect().width);
      setChartWidth(width > 0 ? width : 0);
    };

    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  if (chartData.length === 0) {
    return <div className="h-32 w-full flex items-center justify-center text-xs text-fg3">No data</div>;
  }

  return (
    <div ref={containerRef} className="h-[152px] w-full min-w-0 overflow-hidden">
      {chartWidth > 0 && (
        <AreaChart width={chartWidth} height={CHART_HEIGHT} data={chartData} margin={{ top: 12, right: 8, left: 4, bottom: 2 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
          <XAxis 
            dataKey="ts" 
            tickFormatter={formatTime} 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: '#888', fontSize: 10 }}
            tickMargin={8}
            minTickGap={28}
            interval="preserveStartEnd"
            padding={{ left: 10, right: 18 }}
            height={24}
          />
          <YAxis 
            domain={domain}
            orientation="right" 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: '#888', fontSize: 10 }}
            tickMargin={6}
            tickCount={5}
            width={48}
            tickFormatter={formatBpsTick}
          />
          <Tooltip 
            contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', fontSize: '12px', color: '#fff' }}
            itemStyle={{ color: color }}
            labelFormatter={(label) => formatTime(label as number)}
            formatter={(val: any) => [`${Number(val).toFixed(2)} bps`, 'Spread']}
          />
          {/* P90 reference line (upper band) */}
          <ReferenceLine
            y={p90}
            stroke="#facc15"
            strokeDasharray="4 3"
            strokeWidth={1}
          />
          {/* P10 reference line (lower band) */}
          <ReferenceLine
            y={p10}
            stroke="#60a5fa"
            strokeDasharray="4 3"
            strokeWidth={1}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fillOpacity={1}
            fill={`url(#${gradId})`}
            isAnimationActive={false}
          />
        </AreaChart>
      )}
    </div>
  );
}
