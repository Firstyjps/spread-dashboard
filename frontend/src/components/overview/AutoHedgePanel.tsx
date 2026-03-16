import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../services/api';

interface HedgeEntry {
  ts: number;
  symbol: string;
  delta: number;
  lighter_side: string;
  amount: number;
  status: string;
  tx_hash?: string;
  error?: string;
}

interface HedgeStatus {
  running: boolean;
  symbol: string;
  source_exchange: string;
  poll_interval_s: number;
  min_delta: number;
  last_signed_position: number | null;
  hedges_executed: number;
  consecutive_errors: number;
  started_at: number | null;
  recent_hedges: HedgeEntry[];
}

export const AutoHedgePanel = React.memo(function AutoHedgePanel() {
  const [status, setStatus] = useState<HedgeStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Config inputs
  const [symbol, setSymbol] = useState('XAUTUSDT');
  const [pollInterval, setPollInterval] = useState('2');
  const [minDelta, setMinDelta] = useState('0.001');

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.autoHedgeStatus();
      setStatus(data);
      setError('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch status');
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const iv = setInterval(fetchStatus, 2000);
    return () => clearInterval(iv);
  }, [fetchStatus]);

  const handleStart = async () => {
    setLoading(true);
    try {
      await api.autoHedgeStart({
        symbol,
        poll_interval_s: parseFloat(pollInterval) || 2,
        min_delta: parseFloat(minDelta) || 0.001,
      });
      await fetchStatus();
      setError('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await api.autoHedgeStop();
      await fetchStatus();
      setError('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to stop');
    } finally {
      setLoading(false);
    }
  };

  const running = status?.running ?? false;
  const posLabel = status?.last_signed_position != null
    ? status.last_signed_position > 0
      ? `+${status.last_signed_position} (LONG)`
      : status.last_signed_position < 0
        ? `${status.last_signed_position} (SHORT)`
        : '0 (FLAT)'
    : '–';

  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider">
          Auto-Hedge Monitor
        </h3>
        <span className={`text-xs font-bold px-2 py-0.5 rounded ${
          running
            ? 'bg-green-900/50 text-green-400 border border-green-600/50'
            : 'bg-gray-800 text-gray-500 border border-gray-700'
        }`}>
          {running ? 'ACTIVE' : 'STOPPED'}
        </span>
      </div>

      {/* Status info (when running) */}
      {running && status && (
        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <div>
            <span className="text-gray-500">Symbol:</span>{' '}
            <span className="text-white">{status.symbol}</span>
          </div>
          <div>
            <span className="text-gray-500">Source:</span>{' '}
            <span className="text-yellow-400">BYBIT</span>
            <span className="text-gray-600 ml-1">({status.poll_interval_s}s)</span>
          </div>
          <div>
            <span className="text-gray-500">Bybit Pos:</span>{' '}
            <span className={
              status.last_signed_position != null && status.last_signed_position > 0
                ? 'text-green-400'
                : status.last_signed_position != null && status.last_signed_position < 0
                  ? 'text-red-400'
                  : 'text-gray-400'
            }>
              {posLabel}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Hedges:</span>{' '}
            <span className="text-cyan-400">{status.hedges_executed}</span>
            {status.consecutive_errors > 0 && (
              <span className="text-red-400 ml-2">Err: {status.consecutive_errors}</span>
            )}
          </div>
        </div>
      )}

      {/* Config (when stopped) */}
      {!running && (
        <div className="space-y-2">
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[10px] text-gray-500 uppercase">Symbol</label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-white focus:border-cyan-500 focus:outline-none"
              >
                <option value="BTCUSDT">BTCUSDT</option>
                <option value="ETHUSDT">ETHUSDT</option>
                <option value="HYPEUSDT">HYPEUSDT</option>
                <option value="XAUTUSDT">XAUTUSDT</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {error && (
        <p className="text-xs text-yellow-500">{error}</p>
      )}

      {/* Start / Stop button */}
      <button
        onClick={running ? handleStop : handleStart}
        disabled={loading}
        className={`w-full py-2 rounded font-bold text-xs transition-colors disabled:opacity-50 ${
          running
            ? 'bg-red-600/20 hover:bg-red-600/40 text-red-400 border border-red-600/50'
            : 'bg-cyan-600/20 hover:bg-cyan-600/40 text-cyan-400 border border-cyan-600/50'
        }`}
      >
        {loading ? 'PROCESSING...' : running ? 'STOP AUTO-HEDGE' : 'START AUTO-HEDGE'}
      </button>

      {/* Hedge Log */}
      {status && status.recent_hedges.length > 0 && (
        <div className="border-t border-gray-800 pt-2">
          <label className="text-[10px] text-gray-500 uppercase tracking-wider">Recent Hedges</label>
          <div className="space-y-1 mt-1 max-h-32 overflow-y-auto">
            {[...status.recent_hedges].reverse().slice(0, 10).map((h, i) => (
              <div key={`${h.ts}-${i}`} className="flex items-center gap-2 text-xs font-mono">
                <span className="text-gray-600">
                  {new Date(h.ts * 1000).toLocaleTimeString()}
                </span>
                <span className={h.lighter_side === 'BUY' ? 'text-green-400' : 'text-red-400'}>
                  {h.lighter_side}
                </span>
                <span className="text-gray-400">{h.amount}</span>
                <span className={h.status === 'success' ? 'text-green-500' : 'text-red-500'}>
                  {h.status === 'success' ? 'OK' : 'FAIL'}
                </span>
                {h.error && (
                  <span className="text-red-600 truncate flex-1">{h.error}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});
