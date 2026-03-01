import React, { useState } from 'react';
import { api } from '../../services/api';

interface Props {
  symbol: string;
}


export function ExecutionControl({ symbol }: Props) {
  const [loading, setLoading] = useState(false);

  const handleExecute = async (side: 'LONG_LIGHTER' | 'SHORT_LIGHTER') => {
    const confirmMsg = side === 'LONG_LIGHTER' 
      ? `Confirm: Buy ${symbol} on Lighter & Sell on Bybit?`
      : `Confirm: Sell ${symbol} on Lighter & Buy on Bybit?`;

    if (!window.confirm(confirmMsg)) return;

    setLoading(true);
    try {
      const res = await api.executeArb(symbol, side, 0.01);
      alert(`✅ Success: ${res.detail}`);
    } catch (error) {
      console.error(error);
      alert('❌ Execution Failed! Check backend logs.');
    } finally {
      setLoading(false);
    }
  };

  const handleCloseAll = async () => {
    const confirmMsg = `🚨 EMERGENCY CLOSE: Are you sure you want to close ALL positions for ${symbol}?`;
    if (!window.confirm(confirmMsg)) return;

    setLoading(true);
    try {
      const res = await api.closePositions(symbol);
      alert(`✅ Closed Successfully!`);
    } catch (error) {
      console.error(error);
      alert('❌ Close Failed! Check backend logs immediately.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 mt-4 pt-4 border-t border-gray-800">
      <div className="flex gap-2">
        <button
          onClick={() => handleExecute('LONG_LIGHTER')}
          disabled={loading}
          className="flex-1 bg-green-600/20 hover:bg-green-600/40 text-green-400 border border-green-600/50 py-2 rounded font-bold text-xs transition-colors disabled:opacity-50"
        >
          {loading ? 'EXECUTING...' : 'BUY L / SELL B'}
        </button>
        <button
          onClick={() => handleExecute('SHORT_LIGHTER')}
          disabled={loading}
          className="flex-1 bg-red-600/20 hover:bg-red-600/40 text-red-400 border border-red-600/50 py-2 rounded font-bold text-xs transition-colors disabled:opacity-50"
        >
          {loading ? 'EXECUTING...' : 'SELL L / BUY B'}
        </button>
      </div>

      <button
        onClick={handleCloseAll}
        disabled={loading}
        className="w-full bg-orange-600/20 hover:bg-orange-600/40 text-orange-400 border border-orange-600/50 py-2 rounded font-bold text-xs transition-colors disabled:opacity-50 mt-1"
      >
        {loading ? 'CLOSING POSITIONS...' : '🚨 EMERGENCY CLOSE ALL'}
      </button>
    </div>
  );
}