import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../../services/api';

interface Props {
  symbol: string;
}

interface PositionData {
  amount: number;
  is_long: boolean;
  entry_price: number;
  pnl: number;
  mark_price?: number;
  liq_price?: number;
  leverage?: number;
  funding_paid?: number;
  realized_pnl?: number;
}

interface FundingData {
  bybit_rate: number | null;
  lighter_rate: number | null;
  lighter_8h: number | null;
  net_8h_rate: number | null;
}

interface TheoreticalData {
  entry_bps: number | null;
  current_bps: number | null;
  diff_bps: number | null;
  pnl_usd: number | null;
}

interface TradeLog {
  ts: number;
  action: string;
  symbol: string;
  amount: number;
  status: 'success' | 'failed';
  detail: string;
}

const QUICK_AMOUNTS = [0.001, 0.01, 0.1, 1.0];
const STORAGE_KEY = 'spread-dashboard-trade-log';

function loadTradeLog(): TradeLog[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveTradeLog(logs: TradeLog[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(logs.slice(0, 50)));
}

function formatNum(n: number | undefined, decimals = 3): string {
  if (n == null || isNaN(n)) return '–';
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatPnl(n: number | undefined): string {
  if (n == null || isNaN(n)) return '–';
  const sign = n >= 0 ? '+' : '-';
  return `${sign}$${formatNum(Math.abs(n))}`;
}

export const ExecutionPanel = React.memo(function ExecutionPanel({ symbol }: Props) {
  const [amount, setAmount] = useState('0.01');
  const [loading, setLoading] = useState(false);
  const [bybitPos, setBybitPos] = useState<PositionData | null>(null);
  const [lighterPos, setLighterPos] = useState<PositionData | null>(null);
  const [funding, setFunding] = useState<FundingData | null>(null);
  const [theoretical, setTheoretical] = useState<TheoreticalData | null>(null);
  const [tradeLog, setTradeLog] = useState<TradeLog[]>(loadTradeLog);
  const [posError, setPosError] = useState('');

  // Fetch positions every 5s (now includes funding + theoretical from backend)
  const fetchPositions = useCallback(async () => {
    try {
      const data = await api.positions(symbol);
      setBybitPos(data.bybit);
      setLighterPos(data.lighter);
      setFunding(data.funding || null);
      setTheoretical(data.theoretical || null);
      setPosError('');
    } catch (err: unknown) {
      setPosError(err instanceof Error ? err.message : 'Failed to fetch positions');
    }
  }, [symbol]);

  useEffect(() => {
    fetchPositions();
    const iv = setInterval(fetchPositions, 5000);
    return () => clearInterval(iv);
  }, [fetchPositions]);

  const addLog = (action: string, amt: number, status: 'success' | 'failed', detail: string) => {
    const entry: TradeLog = { ts: Date.now(), action, symbol, amount: amt, status, detail };
    const updated = [entry, ...tradeLog].slice(0, 50);
    setTradeLog(updated);
    saveTradeLog(updated);
  };

  const handleExecute = async (side: 'LONG_LIGHTER' | 'SHORT_LIGHTER') => {
    const amt = parseFloat(amount);
    if (isNaN(amt) || amt <= 0) {
      alert('Please enter a valid amount');
      return;
    }

    const label = side === 'LONG_LIGHTER' ? 'BUY L / SELL B' : 'SELL L / BUY B';
    const confirmMsg = side === 'LONG_LIGHTER'
      ? `Confirm: Buy ${amt} ${symbol} on Lighter & Sell on Bybit?`
      : `Confirm: Sell ${amt} ${symbol} on Lighter & Buy on Bybit?`;

    if (!window.confirm(confirmMsg)) return;

    setLoading(true);
    try {
      const res = await api.executeArb(symbol, side, amt);
      addLog(label, amt, 'success', res.detail || 'OK');
      fetchPositions();
    } catch (error: unknown) {
      addLog(label, amt, 'failed', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const handleCloseAll = async () => {
    if (!window.confirm(`EMERGENCY CLOSE: Close ALL positions for ${symbol}?`)) return;

    setLoading(true);
    try {
      const res = await api.closePositions(symbol);
      addLog('CLOSE ALL', 0, res.status === 'success' ? 'success' : 'failed', res.detail || res.error || 'Done');
      fetchPositions();
    } catch (error: unknown) {
      addLog('CLOSE ALL', 0, 'failed', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  // SL/TP state (upstream price-based approach)
  const [slTpStatus, setSlTpStatus] = useState<any>(null);
  const [slTpEditing, setSlTpEditing] = useState(false);
  const [slInput, setSlInput] = useState('300');
  const [tpInput, setTpInput] = useState('300');
  const [slTpLoading, setSlTpLoading] = useState(false);
  const alertedRef = useRef(false);

  const fetchSlTp = useCallback(async () => {
    try {
      const data = await api.slTpStatus();
      setSlTpStatus(data);
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
      if (!data.triggered) alertedRef.current = false;
    } catch {}
  }, []);

  useEffect(() => {
    fetchSlTp();
    const iv = setInterval(fetchSlTp, 2000);
    return () => clearInterval(iv);
  }, [fetchSlTp]);

  const handleSlTpSet = async () => {
    const sl = parseFloat(slInput) || 0;
    const tp = parseFloat(tpInput) || 0;
    if (sl <= 0 && tp <= 0) return;
    setSlTpLoading(true);
    try {
      await api.slTpStart({ symbol, sl_delta: sl, tp_delta: tp });
      await fetchSlTp();
      setSlTpEditing(false);
    } catch {}
    setSlTpLoading(false);
  };

  const handleSlTpCancel = async () => {
    setSlTpLoading(true);
    try {
      await api.slTpStop();
      await fetchSlTp();
    } catch {}
    setSlTpLoading(false);
  };

  const netPnl = (bybitPos?.pnl || 0) + (lighterPos?.pnl || 0);
  const hasPosition = (bybitPos?.amount || 0) > 0 || (lighterPos?.amount || 0) > 0;

  // Entry BPS: spread at position entry = (lighter_entry - bybit_entry) / bybit_entry * 10000
  const entryBps = (hasPosition && bybitPos?.entry_price && lighterPos?.entry_price && bybitPos.entry_price > 0)
    ? ((lighterPos.entry_price - bybitPos.entry_price) / bybitPos.entry_price) * 10000
    : null;

  // Lighter funding paid (from API)
  const lighterFundingPaid = lighterPos?.funding_paid || 0;

  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider">Execution Panel</h3>
          {entryBps != null && (
            <span className="text-xs font-mono font-bold text-cyan-400">
              Entry: {entryBps >= 0 ? '+' : ''}{entryBps.toFixed(2)} bps
            </span>
          )}
        </div>
        {hasPosition && (
          <span className={`text-xs font-mono font-bold ${netPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            Net PnL: {formatPnl(netPnl)}
          </span>
        )}
      </div>


      {/* Position Cards */}
      <div className="grid grid-cols-2 gap-3">
        <PositionCard exchange="Bybit" pos={bybitPos} />
        <PositionCard exchange="Lighter" pos={lighterPos} />
      </div>

      {posError && (
        <p className="text-xs text-yellow-500">{posError}</p>
      )}

      {/* TP / SL Inline */}
      {hasPosition && (() => {
        const running = slTpStatus?.running;
        const triggered = slTpStatus?.triggered;
        const entryP = slTpStatus?.entry_price;
        const slPrice = entryP && slTpStatus?.sl_delta ? entryP - slTpStatus.sl_delta : null;
        const tpPrice = entryP && slTpStatus?.tp_delta ? entryP + slTpStatus.tp_delta : null;

        return (
          <div className={`border rounded-lg px-3 py-2 ${
            triggered ? 'border-yellow-500/70 bg-yellow-900/10' : 'border-gray-700/50 bg-gray-800/30'
          }`}>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400 font-semibold">TP / SL</span>
              <div className="flex items-center gap-2">
                {triggered ? (
                  <span className="text-xs font-bold text-yellow-400">
                    {slTpStatus.trigger_type} TRIGGERED
                  </span>
                ) : running ? (
                  <span className="text-xs font-mono text-gray-300">
                    <span className="text-green-400">{tpPrice != null ? formatNum(tpPrice) : '–'}</span>
                    {' / '}
                    <span className="text-red-400">{slPrice != null ? formatNum(slPrice) : '–'}</span>
                  </span>
                ) : (
                  <span className="text-xs font-mono text-gray-600">– / –</span>
                )}

                {/* Edit / Cancel button */}
                {triggered ? (
                  <button
                    onClick={async () => {
                      alertedRef.current = false;
                      try { await api.slTpReset(); } catch {}
                      await fetchSlTp();
                    }}
                    className="text-gray-500 hover:text-gray-300 p-1"
                    title="Dismiss"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                  </button>
                ) : running ? (
                  <button
                    onClick={handleSlTpCancel}
                    disabled={slTpLoading}
                    className="text-red-500 hover:text-red-400 p-1"
                    title="Cancel SL/TP"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                  </button>
                ) : (
                  <button
                    onClick={() => setSlTpEditing(!slTpEditing)}
                    className="text-gray-500 hover:text-gray-300 p-1"
                    title="Set TP/SL"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                      <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                    </svg>
                  </button>
                )}
              </div>
            </div>

            {/* Edit mode: input fields */}
            {slTpEditing && !running && !triggered && (
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1">
                  <label className="text-[10px] text-green-400">TP +$</label>
                  <input
                    type="number"
                    value={tpInput}
                    onChange={(e) => setTpInput(e.target.value)}
                    step="10"
                    min="0"
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white font-mono focus:border-green-500 focus:outline-none"
                  />
                </div>
                <div className="flex-1">
                  <label className="text-[10px] text-red-400">SL -$</label>
                  <input
                    type="number"
                    value={slInput}
                    onChange={(e) => setSlInput(e.target.value)}
                    step="10"
                    min="0"
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white font-mono focus:border-red-500 focus:outline-none"
                  />
                </div>
                <button
                  onClick={handleSlTpSet}
                  disabled={slTpLoading}
                  className="mt-3 bg-purple-600/30 hover:bg-purple-600/50 text-purple-400 border border-purple-600/50 px-3 py-1 rounded text-xs font-bold disabled:opacity-50"
                >
                  {slTpLoading ? '...' : 'SET'}
                </button>
              </div>
            )}

            {/* Progress bar when running */}
            {running && entryP != null && slTpStatus?.last_mark_price != null && (
              <div className="mt-1.5 flex items-center gap-1 text-[10px] font-mono">
                <span className="text-red-400">{slPrice != null ? formatNum(slPrice, 0) : ''}</span>
                <div className="flex-1 h-1.5 bg-gray-700 rounded-full relative overflow-hidden">
                  {(() => {
                    const range = (slTpStatus.sl_delta || 500) + (slTpStatus.tp_delta || 500);
                    const dev = slTpStatus.last_mark_price - entryP;
                    const pos = ((dev + (slTpStatus.sl_delta || 500)) / range) * 100;
                    const clamped = Math.max(2, Math.min(98, pos));
                    return (
                      <div
                        className={`absolute top-0 h-full w-1 rounded-full ${dev >= 0 ? 'bg-green-400' : 'bg-red-400'}`}
                        style={{ left: `${clamped}%`, transform: 'translateX(-50%)' }}
                      />
                    );
                  })()}
                </div>
                <span className="text-green-400">{tpPrice != null ? formatNum(tpPrice, 0) : ''}</span>
              </div>
            )}
          </div>
        );
      })()}

      {/* Order Section */}
      <div className="border-t border-gray-800 pt-3 space-y-2">
        <label className="text-xs text-gray-500 uppercase tracking-wider">New Order</label>

        {/* Amount input + quick buttons */}
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            step="0.001"
            min="0"
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white font-mono focus:border-green-500 focus:outline-none"
            placeholder="Amount"
          />
          <span className="text-xs text-gray-500 w-8">
            {symbol.replace('USDT', '').replace('XAUT', 'XAU')}
          </span>
        </div>

        {/* Quick amount buttons */}
        <div className="flex gap-1">
          {QUICK_AMOUNTS.map((q) => (
            <button
              key={q}
              onClick={() => setAmount(String(q))}
              className={`flex-1 text-xs py-1 rounded border transition-colors ${
                amount === String(q)
                  ? 'bg-gray-700 border-gray-500 text-white'
                  : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:border-gray-500'
              }`}
            >
              {q}
            </button>
          ))}
        </div>

        {/* Execute buttons */}
        <div className="flex gap-2">
          <button
            onClick={() => handleExecute('LONG_LIGHTER')}
            disabled={loading}
            className="flex-1 bg-green-600/20 hover:bg-green-600/40 text-green-400 border border-green-600/50 py-3 sm:py-2.5 rounded font-bold text-xs transition-colors disabled:opacity-50"
          >
            {loading ? 'EXECUTING...' : 'BUY L / SELL B'}
          </button>
          <button
            onClick={() => handleExecute('SHORT_LIGHTER')}
            disabled={loading}
            className="flex-1 bg-red-600/20 hover:bg-red-600/40 text-red-400 border border-red-600/50 py-3 sm:py-2.5 rounded font-bold text-xs transition-colors disabled:opacity-50"
          >
            {loading ? 'EXECUTING...' : 'SELL L / BUY B'}
          </button>
        </div>

        {/* Emergency close */}
        {hasPosition && (
          <button
            onClick={handleCloseAll}
            disabled={loading}
            className="w-full bg-orange-600/20 hover:bg-orange-600/40 text-orange-400 border border-orange-600/50 py-2 rounded font-bold text-xs transition-colors disabled:opacity-50"
          >
            {loading ? 'CLOSING...' : '🚨 EMERGENCY CLOSE ALL'}
          </button>
        )}
      </div>

      {/* Trade History */}
      {tradeLog.length > 0 && (
        <div className="border-t border-gray-800 pt-3">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs text-gray-500 uppercase tracking-wider">Recent Trades</label>
            <button
              onClick={() => { setTradeLog([]); saveTradeLog([]); }}
              className="text-[10px] text-gray-600 hover:text-gray-400"
            >
              Clear
            </button>
          </div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {tradeLog.slice(0, 10).map((log) => (
              <div key={`${log.ts}-${log.action}`} className="flex items-center gap-2 text-xs font-mono">
                <span className="text-gray-600">
                  {new Date(log.ts).toLocaleTimeString()}
                </span>
                <span className="text-gray-400 w-20 sm:w-24 truncate">{log.action}</span>
                {log.amount > 0 && (
                  <span className="text-gray-500">{log.amount}</span>
                )}
                <span className={log.status === 'success' ? 'text-green-500' : 'text-red-500'}>
                  {log.status === 'success' ? 'OK' : 'FAIL'}
                </span>
                <span className="text-gray-600 truncate flex-1">{log.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});


const PositionCard = React.memo(function PositionCard({ exchange, pos }: {
  exchange: string;
  pos: PositionData | null;
}) {
  const hasPos = pos && pos.amount > 0;

  return (
    <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-gray-400">{exchange}</span>
        {hasPos && (
          <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
            pos.is_long
              ? 'bg-green-900/50 text-green-400'
              : 'bg-red-900/50 text-red-400'
          }`}>
            {pos.is_long ? 'LONG' : 'SHORT'}
          </span>
        )}
      </div>

      {hasPos ? (
        <div className="space-y-1">
          <div className="text-white font-mono text-sm font-bold">
            {formatNum(pos.amount, 4)}
          </div>
          <div className="grid grid-cols-2 gap-x-2 text-xs">
            <div>
              <span className="text-gray-500">Entry:</span>{' '}
              <span className="text-gray-300 font-mono">{formatNum(pos.entry_price)}</span>
            </div>
            <div>
              <span className="text-gray-500">PnL:</span>{' '}
              <span className={`font-mono font-bold ${pos.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {formatPnl(pos.pnl)}
              </span>
            </div>
            {pos.mark_price != null && pos.mark_price > 0 && (
              <div>
                <span className="text-gray-500">Mark:</span>{' '}
                <span className="text-gray-300 font-mono">{formatNum(pos.mark_price)}</span>
              </div>
            )}
            {pos.liq_price != null && pos.liq_price > 0 && (
              <div>
                <span className="text-gray-500">Liq:</span>{' '}
                <span className="text-yellow-500 font-mono">{formatNum(pos.liq_price)}</span>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="text-gray-600 text-xs py-2">No position</div>
      )}
    </div>
  );
});
