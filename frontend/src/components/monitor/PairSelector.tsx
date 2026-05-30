import React, { useState } from 'react';
import { Settings2 } from 'lucide-react';
import { cn } from '../../lib/cn';

interface PairSelectorProps {
  availablePairs: { id: string; label: string }[];
  selectedPairs: string[];
  onChange: (selected: string[]) => void;
}

export function PairSelector({ availablePairs, selectedPairs, onChange }: PairSelectorProps) {
  const [open, setOpen] = useState(false);
  const selectedAvailableCount = availablePairs.filter((pair) => selectedPairs.includes(pair.id)).length;

  const togglePair = (id: string) => {
    if (selectedPairs.includes(id)) {
      onChange(selectedPairs.filter((p) => p !== id));
    } else {
      onChange([...selectedPairs, id]);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-bg1 border border-bd1 rounded-md text-fg2 hover:text-fg1 hover:bg-bg2 transition-colors"
      >
        <Settings2 size={14} />
        Pairs ({selectedAvailableCount}/{availablePairs.length})
      </button>
      
      {open && (
        <div className="absolute right-0 mt-2 w-56 bg-card border border-bd1 rounded-md shadow-lg p-2 z-10 flex flex-col gap-1">
          {availablePairs.map((pair) => (
            <label key={pair.id} className="flex items-center gap-2 px-2 py-1.5 hover:bg-bg2 rounded cursor-pointer text-sm text-fg2">
              <input
                type="checkbox"
                checked={selectedPairs.includes(pair.id)}
                onChange={() => togglePair(pair.id)}
                className="accent-primary"
              />
              {pair.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
