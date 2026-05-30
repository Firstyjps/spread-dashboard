// file: frontend/src/components/overview/AutoHedgePanel.tsx
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
    const iv = setInterval(fetchStatus, 3000);
    return () => clearInterval(iv);
  }, [fetchStatus]);

  const handleStart = async () => {
    setLoading(true);
    try {
      await api.autoHedgeStart({
        symbol,
        poll_interval_s: 0.5,
        min_delta: 0.001,
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

  return (
    <div className="bg-card border border-bd1 rounded-lg px-4 py-3 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
      {/* Configuration & Details Section */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 w-full sm:w-auto">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-warn" />
          <span className="font-mono font-bold text-fg1 tracking-wider uppercase">Auto-Hedge</span>
        </div>

        {/* Pair selector */}
        <div className="flex items-center gap-1.5 font-mono">
          <span className="text-[10px] text-fg3 uppercase font-bold">Pair:</span>
          {running ? (
            <span className="text-fg1 font-bold">{status?.symbol.replace('USDT', '')}</span>
          ) : (
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-bg1 border border-bd2 rounded px-2 py-0.5 text-fg1 font-semibold text-xs focus:outline-none focus:border-info cursor-pointer transition-colors hover:border-bd2"
            >
              <option value="XAUTUSDT">XAUT (Gold)</option>
              <option value="HYPEUSDT">HYPE</option>
              <option value="BTCUSDT">BTC</option>
              <option value="ETHUSDT">ETH</option>
            </select>
          )}
        </div>



        {/* Stats counter when running */}
        {running && status && (
          <div className="flex items-center gap-4 font-mono text-[10px] text-fg2 border-l border-bd2 pl-6">
            <div>
              Hedges: <span className="text-info font-bold">{status.hedges_executed}</span>
            </div>
            {status.consecutive_errors > 0 && (
              <div className="text-short font-bold animate-pulse-fast">
                Errors: {status.consecutive_errors}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Controller Buttons Section */}
      <div className="flex items-center gap-3 shrink-0 w-full sm:w-auto justify-end border-t sm:border-t-0 border-bd1 pt-2.5 sm:pt-0">
        {error && (
          <span className="text-[10px] font-mono text-short mr-2 truncate max-w-[120px]">{error}</span>
        )}

        {/* Status Badge */}
        {running ? (
          <span className="bg-long/10 border border-long/20 text-long px-2.5 py-1 rounded text-[10px] font-black font-mono flex items-center gap-1.5 shadow-[0_0_12px_rgba(0,201,107,0.1)]">
            <span className="w-1.5 h-1.5 rounded-full bg-long animate-pulse-fast" />
            RUNNING
          </span>
        ) : (
          <span className="bg-short/10 border border-short/20 text-short px-2.5 py-1 rounded text-[10px] font-black font-mono flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-short" />
            STOPPED
          </span>
        )}

        {/* Start / Stop Trigger */}
        <button
          onClick={running ? handleStop : handleStart}
          disabled={loading}
          className={`px-3 py-1.5 rounded font-mono font-bold text-xs uppercase border tracking-wider transition-all duration-150 ${
            running
              ? 'bg-short/10 border-short/30 text-short btn-glow-red hover:bg-short/20'
              : 'bg-long/10 border-long/30 text-long btn-glow-green hover:bg-long/20'
          }`}
        >
          {loading ? '...' : running ? 'Stop' : 'Start'}
        </button>
      </div>
    </div>
  );
});
