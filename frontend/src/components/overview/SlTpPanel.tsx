import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../../services/api';

interface TriggerEntry {
  ts: number;
  type: string;
  symbol: string;
  mark_price: number;
  entry_price: number;
  deviation: number;
  status: string;
  detail?: string;
  error?: string;
}

interface SlTpStatus {
  running: boolean;
  symbol: string;
  sl_delta: number;
  tp_delta: number;
  poll_interval_s: number;
  last_mark_price: number | null;
  entry_price: number | null;
  triggered: boolean;
  trigger_type: string | null;
  consecutive_errors: number;
  started_at: number | null;
  recent_triggers: TriggerEntry[];
}

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null || isNaN(n)) return '–';
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export const SlTpPanel = React.memo(function SlTpPanel() {
  const [status, setStatus] = useState<SlTpStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const alertedRef = useRef(false);

  // Config inputs
  const [symbol, setSymbol] = useState('XAUTUSDT');
  const [slDelta, setSlDelta] = useState('300');
  const [tpDelta, setTpDelta] = useState('300');

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.slTpStatus();
      setStatus(data);
      setError('');

      // Sound alert on trigger
      if (data.triggered && !alertedRef.current) {
        alertedRef.current = true;
        try {
          const ctx = new AudioContext();
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.frequency.value = data.trigger_type === 'SL' ? 440 : 880;
          gain.gain.value = 0.3;
          osc.start();
          setTimeout(() => { osc.stop(); ctx.close(); }, 500);
        } catch {}
      }
      if (!data.triggered) {
        alertedRef.current = false;
      }
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
    const sl = parseFloat(slDelta) || 0;
    const tp = parseFloat(tpDelta) || 0;
    if (sl <= 0 && tp <= 0) {
      setError('Set at least one of SL or TP > 0');
      return;
    }
    setLoading(true);
    try {
      await api.slTpStart({ symbol, sl_delta: sl, tp_delta: tp });
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
      await api.slTpStop();
      await fetchStatus();
      setError('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to stop');
    } finally {
      setLoading(false);
    }
  };

  const running = status?.running ?? false;
  const triggered = status?.triggered ?? false;

  // Compute SL/TP price levels
  const entryPrice = status?.entry_price;
  const slPrice = entryPrice != null && status?.sl_delta ? entryPrice - status.sl_delta : null;
  const tpPrice = entryPrice != null && status?.tp_delta ? entryPrice + status.tp_delta : null;

  return (
    <div className={`bg-gray-900/60 border rounded-lg p-4 space-y-3 ${
      triggered
        ? 'border-yellow-500/70 bg-yellow-900/10'
        : 'border-gray-800'
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider">
          SL / TP Monitor
        </h3>
        <span className={`text-xs font-bold px-2 py-0.5 rounded ${
          triggered
            ? 'bg-yellow-900/50 text-yellow-400 border border-yellow-600/50'
            : running
              ? 'bg-green-900/50 text-green-400 border border-green-600/50'
              : 'bg-gray-800 text-gray-500 border border-gray-700'
        }`}>
          {triggered ? `${status?.trigger_type} TRIGGERED` : running ? 'ACTIVE' : 'STOPPED'}
        </span>
      </div>

      {/* Status info (when running or triggered) */}
      {(running || triggered) && status && (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div>
              <span className="text-gray-500">Symbol:</span>{' '}
              <span className="text-white">{status.symbol}</span>
            </div>
            <div>
              <span className="text-gray-500">Entry:</span>{' '}
              <span className="text-gray-300">{fmt(entryPrice)}</span>
            </div>
            <div>
              <span className="text-gray-500">Mark:</span>{' '}
              <span className="text-white font-bold">{fmt(status.last_mark_price)}</span>
            </div>
            <div>
              <span className="text-gray-500">Dev:</span>{' '}
              {status.last_mark_price != null && entryPrice != null ? (() => {
                const dev = status.last_mark_price - entryPrice;
                return (
                  <span className={`font-bold ${dev >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {dev >= 0 ? '+' : ''}{fmt(dev)}
                  </span>
                );
              })() : <span className="text-gray-500">–</span>}
            </div>
          </div>

          {/* Price bar: SL ← [mark] → TP */}
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-red-400 w-16 text-right truncate" title={slPrice != null ? slPrice.toFixed(2) : ''}>
              {slPrice != null ? fmt(slPrice, 0) : '–'}
            </span>
            <div className="flex-1 h-2 bg-gray-800 rounded-full relative overflow-hidden">
              {status.last_mark_price != null && entryPrice != null && (() => {
                const range = (status.sl_delta || 500) + (status.tp_delta || 500);
                const dev = status.last_mark_price - entryPrice;
                const pos = ((dev + (status.sl_delta || 500)) / range) * 100;
                const clamped = Math.max(2, Math.min(98, pos));
                return (
                  <div
                    className={`absolute top-0 h-full w-1.5 rounded-full ${
                      dev >= 0 ? 'bg-green-400' : 'bg-red-400'
                    }`}
                    style={{ left: `${clamped}%`, transform: 'translateX(-50%)' }}
                  />
                );
              })()}
            </div>
            <span className="text-green-400 w-16 truncate" title={tpPrice != null ? tpPrice.toFixed(2) : ''}>
              {tpPrice != null ? fmt(tpPrice, 0) : '–'}
            </span>
          </div>

          {status.consecutive_errors > 0 && (
            <p className="text-xs text-red-400">Errors: {status.consecutive_errors}</p>
          )}
        </div>
      )}

      {/* Config (when stopped and not triggered) */}
      {!running && !triggered && (
        <div className="space-y-2">
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[10px] text-gray-500 uppercase">Symbol</label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-white focus:border-purple-500 focus:outline-none"
              >
                <option value="BTCUSDT">BTCUSDT</option>
                <option value="ETHUSDT">ETHUSDT</option>
                <option value="HYPEUSDT">HYPEUSDT</option>
                <option value="XAUTUSDT">XAUTUSDT</option>
              </select>
            </div>
            <div className="w-24">
              <label className="text-[10px] text-red-400 uppercase">SL ($)</label>
              <input
                type="number"
                value={slDelta}
                onChange={(e) => setSlDelta(e.target.value)}
                step="10"
                min="0"
                placeholder="300"
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-white font-mono focus:border-red-500 focus:outline-none"
              />
            </div>
            <div className="w-24">
              <label className="text-[10px] text-green-400 uppercase">TP ($)</label>
              <input
                type="number"
                value={tpDelta}
                onChange={(e) => setTpDelta(e.target.value)}
                step="10"
                min="0"
                placeholder="300"
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-white font-mono focus:border-green-500 focus:outline-none"
              />
            </div>
          </div>
        </div>
      )}

      {error && (
        <p className="text-xs text-yellow-500">{error}</p>
      )}

      {/* Start / Stop button */}
      {!triggered && (
        <button
          onClick={running ? handleStop : handleStart}
          disabled={loading}
          className={`w-full py-2 rounded font-bold text-xs transition-colors disabled:opacity-50 ${
            running
              ? 'bg-red-600/20 hover:bg-red-600/40 text-red-400 border border-red-600/50'
              : 'bg-purple-600/20 hover:bg-purple-600/40 text-purple-400 border border-purple-600/50'
          }`}
        >
          {loading ? 'PROCESSING...' : running ? 'STOP SL/TP' : 'START SL/TP'}
        </button>
      )}

      {/* Triggered alert — reset button */}
      {triggered && (
        <div className="space-y-2">
          <div className="text-center text-sm font-bold text-yellow-400">
            {status?.trigger_type === 'SL' ? 'STOP LOSS' : 'TAKE PROFIT'} triggered — positions closed
          </div>
          <button
            onClick={async () => {
              alertedRef.current = false;
              try { await api.slTpReset(); } catch {}
              await fetchStatus();
            }}
            className="w-full py-2 rounded font-bold text-xs bg-gray-700/50 hover:bg-gray-600/50 text-gray-300 border border-gray-600"
          >
            DISMISS
          </button>
        </div>
      )}

      {/* Trigger Log */}
      {status && status.recent_triggers.length > 0 && (
        <div className="border-t border-gray-800 pt-2">
          <label className="text-[10px] text-gray-500 uppercase tracking-wider">Trigger Log</label>
          <div className="space-y-1 mt-1 max-h-24 overflow-y-auto">
            {[...status.recent_triggers].reverse().slice(0, 5).map((t, i) => (
              <div key={`${t.ts}-${i}`} className="flex items-center gap-2 text-xs font-mono">
                <span className="text-gray-600">
                  {new Date(t.ts * 1000).toLocaleTimeString()}
                </span>
                <span className={t.type === 'SL' ? 'text-red-400' : 'text-green-400'}>
                  {t.type}
                </span>
                <span className="text-gray-400">
                  @{fmt(t.mark_price)}
                </span>
                <span className={t.status === 'success' ? 'text-green-500' : 'text-red-500'}>
                  {t.status === 'success' ? 'OK' : 'FAIL'}
                </span>
                {t.error && (
                  <span className="text-red-600 truncate flex-1">{t.error}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});
