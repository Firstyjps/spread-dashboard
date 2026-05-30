import React from 'react';
import { cn } from '../../lib/cn';
import type { MonitorTimeframe } from '../../services/api';

interface Props {
  timeframe: MonitorTimeframe;
  onChange: (timeframe: MonitorTimeframe) => void;
}

const OPTIONS: { value: MonitorTimeframe; label: string }[] = [
  { value: 'raw', label: 'Live' },
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1h' },
  { value: '4h', label: '4h' },
];

export function TimeframeToggle({ timeframe, onChange }: Props) {
  return (
    <div className="flex bg-bg2 rounded-md p-1 border border-bd1">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            'px-2.5 py-1 text-xs font-medium rounded-sm transition-colors',
            timeframe === opt.value ? 'bg-bg3 text-fg1 shadow-sm' : 'text-fg3 hover:text-fg2',
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
