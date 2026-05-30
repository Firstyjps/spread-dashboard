import React, { useMemo } from 'react';
import { AreaChart, Area, ReferenceLine, ResponsiveContainer, YAxis, XAxis, CartesianGrid, Tooltip } from 'recharts';

export type ChartDataPoint = {
  ts: number;
  value: number;
};

interface Props {
  data: ChartDataPoint[];
  color: string;
}

function computePercentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

export function SpreadMiniChart({ data, color }: Props) {
  if (!data || data.length === 0) {
    return <div className="h-32 w-full flex items-center justify-center text-xs text-fg3">No data</div>;
  }

  const { p10, p90 } = useMemo(() => {
    const values = data.map(d => d.value).filter(v => v != null);
    const sorted = [...values].sort((a, b) => a - b);
    return {
      p10: computePercentile(sorted, 10),
      p90: computePercentile(sorted, 90),
    };
  }, [data]);

  const formatTime = (ts: number) => {
    const d = new Date(ts);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  const gradId = `grad-${color.replace('#', '')}`;

  return (
    <div className="h-36 w-full -ml-4">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 0, left: 0, bottom: 0 }}>
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
            minTickGap={20}
          />
          <YAxis 
            domain={['auto', 'auto']} 
            orientation="right" 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: '#888', fontSize: 10 }}
            width={35}
            tickFormatter={(val) => val.toFixed(1)}
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
            label={{ value: `P90: ${p90.toFixed(1)}`, position: 'right', fill: '#facc15', fontSize: 9 }}
          />
          {/* P10 reference line (lower band) */}
          <ReferenceLine
            y={p10}
            stroke="#60a5fa"
            strokeDasharray="4 3"
            strokeWidth={1}
            label={{ value: `P10: ${p10.toFixed(1)}`, position: 'right', fill: '#60a5fa', fontSize: 9 }}
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
      </ResponsiveContainer>
    </div>
  );
}
