// file: frontend/src/components/overview/SpreadChart.tsx
import React from 'react';
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

export function SpreadChart({ symbol }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['spreads', symbol],
    queryFn: () => api.spreads(symbol, 300),
    refetchInterval: 3000,
  });

  const history = data?.history ?? [];

  // Convert to bps for display
  const chartData = history.map((row: any) => ({
    time: new Date(row.ts).toLocaleTimeString(),
    mid_spread: +(row.exchange_spread_mid * 10000).toFixed(2),
    long_spread: +(row.long_spread * 10000).toFixed(2),
    short_spread: +(row.short_spread * 10000).toFixed(2),
  }));

  return (
    <section>
      <h2 className="text-sm font-semibold text-gray-400 uppercase mb-3">
        Spread Chart — {symbol} (bps)
      </h2>
      <div className="h-64 bg-gray-900 rounded-lg border border-gray-800 p-3">
        {chartData.length < 2 ? (
          <div className="h-full flex items-center justify-center text-gray-500 text-sm">
            {isLoading ? 'Loading...' : `Collecting data... (${chartData.length} points)`}
          </div>
        ) : (
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
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <ReferenceLine y={0} stroke="#4b5563" strokeDasharray="3 3" />
              <Line
                type="monotone"
                dataKey="mid_spread"
                stroke="#34d399"
                strokeWidth={2}
                dot={false}
                name="Mid Spread"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="long_spread"
                stroke="#60a5fa"
                strokeWidth={1}
                dot={false}
                name="Long Spread"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="short_spread"
                stroke="#f87171"
                strokeWidth={1}
                dot={false}
                name="Short Spread"
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
