import React, { useState, useEffect, useCallback } from 'react';
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

function formatNum(n: number | undefined, decimals = 2): string {
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
  const [tradeLog, setTradeLog] = useState<TradeLog[]>(loadTradeLog);
  const [posError, setPosError] = useState('');

  // Fetch positions every 5s
  const fetchPositions = useCallback(async () => {
    try {
      const data = await api.positions(symbol);
      setBybitPos(data.bybit);
      setLighterPos(data.lighter);
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

  const netPnl = (bybitPos?.pnl || 0) + (lighterPos?.pnl || 0);
  const hasPosition = (bybitPos?.amount || 0) > 0 || (lighterPos?.amount || 0) > 0;

  // Entry BPS: spread at position entry = (lighter_entry - bybit_entry) / bybit_entry * 10000
  const entryBps = (hasPosition && bybitPos?.entry_price && lighterPos?.entry_price && bybitPos.entry_price > 0)
    ? ((lighterPos.entry_price - bybitPos.entry_price) / bybitPos.entry_price) * 10000
    : null;

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
                  {log.status === 'success' ? '✅' : '❌'}
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
