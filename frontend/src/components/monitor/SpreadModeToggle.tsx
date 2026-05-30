import React from 'react';
import { cn } from '../../lib/cn';

export type SpreadMode = 'executable' | 'mid' | 'net';

interface Props {
  mode: SpreadMode;
  onChange: (mode: SpreadMode) => void;
}

export function SpreadModeToggle({ mode, onChange }: Props) {
  return (
    <div className="flex bg-bg2 rounded-md p-1 border border-bd1">
      <button
        onClick={() => onChange('executable')}
        className={cn("px-3 py-1 text-xs font-medium rounded-sm transition-colors", mode === 'executable' ? 'bg-bg3 text-fg1 shadow-sm' : 'text-fg3 hover:text-fg2')}
      >
        Executable
      </button>
      <button
        onClick={() => onChange('mid')}
        className={cn("px-3 py-1 text-xs font-medium rounded-sm transition-colors", mode === 'mid' ? 'bg-bg3 text-fg1 shadow-sm' : 'text-fg3 hover:text-fg2')}
      >
        Mid
      </button>
      <button
        onClick={() => onChange('net')}
        className={cn("px-3 py-1 text-xs font-medium rounded-sm transition-colors", mode === 'net' ? 'bg-bg3 text-fg1 shadow-sm' : 'text-fg3 hover:text-fg2')}
      >
        Net
      </button>
    </div>
  );
}
