import React from 'react';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';

export type ChartDataPoint = {
  ts: number;
  value: number;
};

interface Props {
  data: ChartDataPoint[];
  color: string;
}

export function SpreadMiniChart({ data, color }: Props) {
  if (!data || data.length === 0) {
    return <div className="h-12 w-full flex items-center justify-center text-xs text-fg3">No data</div>;
  }

  return (
    <div className="h-12 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <YAxis domain={['auto', 'auto']} hide />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
