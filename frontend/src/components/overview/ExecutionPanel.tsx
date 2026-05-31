// file: frontend/src/components/overview/ExecutionPanel.tsx
import React, { useState, useEffect, useCallback, useRef, forwardRef, useImperativeHandle } from 'react';
import { api } from '../../services/api';
import { PositionData, ArbFundingData, TheoreticalData } from '../../types/api';

interface Props {
  symbol: string;
  onTradeExecuted?: (message: string) => void;
}

interface TradeLog {
  ts: number;
  action: string;
  symbol: string;
  amount: number;
  status: 'success' | 'failed';
  detail: string;
}

const QUICK_AMOUNTS = [1, 2, 4, 5];
const STORAGE_KEY = 'alphast-trade-log';

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
  return `${sign}$${formatNum(Math.abs(n), 2)}`;
}

export const ExecutionPanel = React.memo(
  forwardRef<{ executeBuy: () => void; executeSell: () => void }, Props>(function ExecutionPanel(
    { symbol, onTradeExecuted },
    ref
  ) {
    const [amount, setAmount] = useState('1');
    const [loading, setLoading] = useState(false);
    const [bybitPos, setBybitPos] = useState<PositionData | null>(null);
    const [lighterPos, setLighterPos] = useState<PositionData | null>(null);
    const [funding, setFunding] = useState<ArbFundingData | null>(null);
    const [theoretical, setTheoretical] = useState<TheoreticalData | null>(null);
    const [tradeLog, setTradeLog] = useState<TradeLog[]>(loadTradeLog);
    const [posError, setPosError] = useState('');

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
      const iv = setInterval(fetchPositions, 4000);
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
      const confirmMsg =
        side === 'LONG_LIGHTER'
          ? `Confirm Execution: BUY ${amt} ${symbol.replace('USDT', '')} Lighter & SELL Bybit?`
          : `Confirm Execution: SELL ${amt} ${symbol.replace('USDT', '')} Lighter & BUY Bybit?`;

      if (!window.confirm(confirmMsg)) return;

      setLoading(true);
      try {
        const res = await api.executeArb(symbol, side, amt);
        const executionStatus = res.status === 'success' ? 'success' : 'failed';
        addLog(label, amt, executionStatus, res.detail || 'Executed');
        if (executionStatus === 'success' && onTradeExecuted) {
          onTradeExecuted(`↑ ${label} · ${amt} ${symbol.replace('USDT', '').replace('XAUT', 'XAU')} @ market`);
        }
        fetchPositions();
      } catch (error: unknown) {
        const errMsg = error instanceof Error ? error.message : 'Unknown execution error';
        addLog(label, amt, 'failed', errMsg);
      } finally {
        setLoading(false);
      }
    };

    // Expose functions for keyboard shortcuts
    useImperativeHandle(ref, () => ({
      executeBuy: () => handleExecute('LONG_LIGHTER'),
      executeSell: () => handleExecute('SHORT_LIGHTER'),
    }));

    const handleCloseAll = async () => {
      if (!window.confirm(`EMERGENCY CLOSE: Close ALL paired positions for ${symbol}?`)) return;

      setLoading(true);
      try {
        const res = await api.closePositions(symbol);
        addLog('CLOSE ALL', 0, res.status === 'success' ? 'success' : 'failed', res.detail || res.error || 'Done');
        if (onTradeExecuted) {
          onTradeExecuted(`🚨 CLOSED ALL POSITIONS FOR ${symbol.replace('USDT', '')}`);
        }
        fetchPositions();
      } catch (error: unknown) {
        addLog('CLOSE ALL', 0, 'failed', error instanceof Error ? error.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    // SL/TP state
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
        if (data.triggered && !alertedRef.current) {
          alertedRef.current = true;
          try {
            const ctx = new AudioContext();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = data.trigger_type === 'SL' ? 440 : 880;
            gain.gain.value = 0.2;
            osc.start();
            setTimeout(() => {
              osc.stop();
              ctx.close();
            }, 400);
          } catch {}
        }
        if (!data.triggered) alertedRef.current = false;
      } catch {}
    }, []);

    useEffect(() => {
      fetchSlTp();
      const iv = setInterval(fetchSlTp, 2500);
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

    const entryBps =
      hasPosition && bybitPos?.entry_price && lighterPos?.entry_price && bybitPos.entry_price > 0
        ? ((lighterPos.entry_price - bybitPos.entry_price) / bybitPos.entry_price) * 10000
        : null;

    return (
      <div className="bg-card border border-bd1 rounded-lg p-4 space-y-4 flex flex-col min-h-0">
        {/* Panel Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <h3 className="text-[10px] font-bold text-fg3 uppercase tracking-wider">Execution Desk</h3>
            {entryBps != null && (
              <span className="bg-info/10 border border-info/20 text-info px-1.5 py-0.5 rounded text-[9px] font-mono font-bold">
                ENTRY SPREAD: {entryBps >= 0 ? '+' : ''}
                {entryBps.toFixed(2)} bps
              </span>
            )}
          </div>
          {hasPosition && (
            <span
              className={`font-mono text-xs font-black ${netPnl >= 0 ? 'text-long' : 'text-short'}`}
            >
              NET PNL: {formatPnl(netPnl)}
            </span>
          )}
        </div>

        {/* Position Occupied vs Empty side-by-side cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <PositionCard exchange="Bybit" pos={bybitPos} />
          <PositionCard exchange="Lighter" pos={lighterPos} />
        </div>

        {posError && <p className="text-[10px] font-mono text-short">{posError}</p>}

        {/* Inline SL/TP range tracking bar */}
        {hasPosition && (() => {
          const running = slTpStatus?.running;
          const triggered = slTpStatus?.triggered;
          const entryP = slTpStatus?.entry_price;
          const slPrice = entryP && slTpStatus?.sl_delta ? entryP - slTpStatus.sl_delta : null;
          const tpPrice = entryP && slTpStatus?.tp_delta ? entryP + slTpStatus.tp_delta : null;

          return (
            <div
              className={`border rounded-lg px-3 py-2 ${
                triggered
                  ? 'border-warn/40 bg-warn/5'
                  : 'border-bd1 bg-card/40'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-fg2 uppercase font-bold font-mono">Arb TP / SL Protect</span>
                <div className="flex items-center gap-2">
                  {triggered ? (
                    <span className="text-[10px] font-mono font-black text-warn animate-pulse-fast">
                      {slTpStatus.trigger_type} TRIGGERED
                    </span>
                  ) : running ? (
                    <span className="text-[10px] font-mono font-bold text-fg1">
                      <span className="text-long">{tpPrice != null ? formatNum(tpPrice, 1) : '–'}</span>
                      <span className="text-fg3 px-1">/</span>
                      <span className="text-short">{slPrice != null ? formatNum(slPrice, 1) : '–'}</span>
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono text-fg3">PROTECTION INACTIVE</span>
                  )}

                  {/* Edit / Dismiss */}
                  {triggered ? (
                    <button
                      onClick={async () => {
                        alertedRef.current = false;
                        try {
                          await api.slTpReset();
                        } catch {}
                        await fetchSlTp();
                      }}
                      className="text-fg2 hover:text-fg1 p-0.5"
                      title="Dismiss alert"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </button>
                  ) : running ? (
                    <button
                      onClick={handleSlTpCancel}
                      disabled={slTpLoading}
                      className="text-short hover:text-red-400 p-0.5"
                      title="Cancel protection"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </button>
                  ) : (
                    <button
                      onClick={() => setSlTpEditing(!slTpEditing)}
                      className="text-fg2 hover:text-fg1 p-0.5"
                      title="Set protection rules"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                        <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>

              {/* Edit forms */}
              {slTpEditing && !running && !triggered && (
                <div className="mt-2 flex items-center gap-2 font-mono">
                  <div className="flex-1">
                    <label className="text-[9px] text-long font-bold uppercase">TP Target (+$)</label>
                    <input
                      type="number"
                      value={tpInput}
                      onChange={(e) => setTpInput(e.target.value)}
                      step="10"
                      min="0"
                      className="w-full bg-bg1 border border-bd2 rounded px-2.5 py-1 text-xs text-fg1 font-bold focus:border-long focus:outline-none"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-[9px] text-short font-bold uppercase">SL Boundary (-$)</label>
                    <input
                      type="number"
                      value={slInput}
                      onChange={(e) => setSlInput(e.target.value)}
                      step="10"
                      min="0"
                      className="w-full bg-bg1 border border-bd2 rounded px-2.5 py-1 text-xs text-fg1 font-bold focus:border-short focus:outline-none"
                    />
                  </div>
                  <button
                    onClick={handleSlTpSet}
                    disabled={slTpLoading}
                    className="mt-3.5 bg-accent-indigo/15 hover:bg-accent-indigo/20 text-accent-indigo border border-accent-indigo/30 px-3 py-1 rounded text-xs font-bold font-mono transition-colors disabled:opacity-50"
                  >
                    {slTpLoading ? '...' : 'ARM'}
                  </button>
                </div>
              )}

              {/* Protection progress bar */}
              {running && entryP != null && slTpStatus?.last_mark_price != null && (
                <div className="mt-1.5 flex items-center gap-2 text-[9px] font-mono font-bold">
                  <span className="text-short">{slPrice != null ? formatNum(slPrice, 0) : ''}</span>
                  <div className="flex-1 h-1 bg-bd2 rounded-full relative overflow-hidden">
                    {(() => {
                      const range = (slTpStatus.sl_delta || 500) + (slTpStatus.tp_delta || 500);
                      const dev = slTpStatus.last_mark_price - entryP;
                      const pos = ((dev + (slTpStatus.sl_delta || 500)) / range) * 100;
                      const clamped = Math.max(2, Math.min(98, pos));
                      return (
                        <div
                          className={`absolute top-0 h-full w-1 rounded-full ${
                            dev >= 0 ? 'bg-long' : 'bg-short'
                          }`}
                          style={{ left: `${clamped}%`, transform: 'translateX(-50%)' }}
                        />
                      );
                    })()}
                  </div>
                  <span className="text-long">{tpPrice != null ? formatNum(tpPrice, 0) : ''}</span>
                </div>
              )}
            </div>
          );
        })()}

        {/* Order inputs and actions */}
        <div className="border-t border-bd1/50 pt-3 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-fg3 uppercase tracking-wider">New Arbitrage Order</span>
            <span className="text-[10px] font-mono text-fg3 font-bold">MARKET EXECUTIVE</span>
          </div>

          <div className="flex items-stretch gap-2.5">
            {/* Input field */}
            <div className="flex-1 flex items-center bg-bg1 border border-bd2 rounded-md px-3 focus-within:border-warn transition-colors">
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                step="1"
                min="0"
                className="w-full bg-transparent border-0 outline-none text-fg1 text-sm font-mono font-bold py-2 focus:ring-0"
                placeholder="0.00"
              />
              <span className="text-xs font-mono font-bold text-fg3 shrink-0 uppercase select-none">
                {symbol.replace('USDT', '').replace('XAUT', 'XAU')}
              </span>
            </div>

            {/* Presets */}
            <div className="flex gap-1">
              {QUICK_AMOUNTS.map((q) => {
                const isDefault = q === 1;
                const isSelected = amount === String(q);
                return (
                  <button
                    key={q}
                    onClick={() => setAmount(String(q))}
                    className={`px-3.5 rounded-md font-mono text-xs font-bold border transition-colors select-none ${
                      isSelected
                        ? 'bg-warn/15 border-warn/50 text-warn'
                        : 'bg-bg1 border-bd2 text-fg2 hover:text-fg1 hover:border-bd2'
                    }`}
                  >
                    {q}
                    {isDefault && <span className="text-[9px] text-warn ml-0.5">★</span>}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Execution Buttons (2-column layout) */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <button
                onClick={() => handleExecute('LONG_LIGHTER')}
                disabled={loading}
                className="w-full bg-long/10 border border-long/30 text-long py-2.5 rounded-md font-bold text-xs btn-glow-green select-none disabled:opacity-50"
              >
                {loading ? 'EXECUTING...' : 'BUY L / SELL B'}
              </button>
              <div className="text-[9px] text-fg3 font-bold font-mono tracking-wide text-center mt-1">
                LONG LIGHTER · SHORT BYBIT
              </div>
            </div>
            <div>
              <button
                onClick={() => handleExecute('SHORT_LIGHTER')}
                disabled={loading}
                className="w-full bg-short/10 border border-short/30 text-short py-2.5 rounded-md font-bold text-xs btn-glow-red select-none disabled:opacity-50"
              >
                {loading ? 'EXECUTING...' : 'SELL L / BUY B'}
              </button>
              <div className="text-[9px] text-fg3 font-bold font-mono tracking-wide text-center mt-1">
                SHORT LIGHTER · LONG BYBIT
              </div>
            </div>
          </div>

          {/* Emergency close */}
          {hasPosition && (
            <button
              onClick={handleCloseAll}
              disabled={loading}
              className="w-full bg-warn/10 hover:bg-warn/20 border border-warn/30 text-warn py-2 rounded-md font-mono font-bold text-xs select-none tracking-wider transition-colors disabled:opacity-50"
            >
              {loading ? 'CLOSING...' : '🚨 EMERGENCY CLOSE ALL SPREADS'}
            </button>
          )}
        </div>

        {/* Trade Log */}
        {tradeLog.length > 0 && (
          <div className="border-t border-bd1/50 pt-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-bold text-fg3 uppercase tracking-wider">Local Executions Log</span>
              <button
                onClick={() => {
                  setTradeLog([]);
                  saveTradeLog([]);
                }}
                className="text-[9px] font-mono text-fg3 hover:text-fg2"
              >
                Clear Log
              </button>
            </div>
            <div className="space-y-1.5 max-h-[100px] overflow-y-auto font-mono text-[10px]">
              {tradeLog.slice(0, 10).map((log, index) => (
                <div
                  key={`${log.ts}-${index}`}
                  className="border-b border-bd1/20 pb-1 text-fg2"
                  title={log.detail}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-fg3 shrink-0">
                        {new Date(log.ts).toLocaleTimeString(undefined, { hour12: false })}
                      </span>
                      <span className="text-fg1 font-bold shrink-0">{log.action}</span>
                      <span className="text-fg2 font-semibold shrink-0">{log.amount} XAU</span>
                    </div>
                    <span className={log.status === 'success' ? 'text-long' : 'text-short'}>
                      {log.status === 'success' ? 'OK' : 'FAIL'}
                    </span>
                  </div>
                  {log.status === 'failed' && log.detail && (
                    <div className="mt-0.5 truncate text-[9px] text-short/80">
                      {log.detail}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  })
);

const PositionCard = React.memo(function PositionCard({
  exchange,
  pos,
}: {
  exchange: string;
  pos: PositionData | null;
}) {
  const hasPos = pos && pos.amount > 0;

  return (
    <div
      className={`rounded-lg p-3 border transition-colors duration-150 ${
        hasPos
          ? 'bg-card border-bd2 shadow-[0_0_12px_rgba(255,255,255,0.02)]'
          : 'bg-card/30 border-bd1 opacity-50'
      }`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] font-bold text-fg2 uppercase">{exchange}</span>
        {hasPos && (
          <span
            className={`text-[9px] font-black px-1.5 py-0.5 rounded ${
              pos.is_long
                ? 'bg-long/10 text-long border border-long/20'
                : 'bg-short/10 text-short border border-short/20'
            }`}
          >
            {pos.is_long ? 'LONG' : 'SHORT'}
          </span>
        )}
      </div>

      {hasPos ? (
        <div className="space-y-1 text-xs font-mono">
          <div className="flex justify-between">
            <span className="text-fg3 text-[10px]">Position Size</span>
            <span className="text-fg1 font-bold font-mono">
              {formatNum(pos.amount, 4)} <span className="text-[10px] text-fg3 font-normal">XAU</span>
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg3 text-[10px]">Entry Price</span>
            <span className="text-fg2">{formatNum(pos.entry_price, 2)}</span>
          </div>
          <div className="flex justify-between border-t border-bd1/50 pt-1 mt-1">
            <span className="text-fg3 text-[10px]">Unrealized PnL</span>
            <span className={`font-black ${pos.pnl >= 0 ? 'text-long' : 'text-short'}`}>
              {formatPnl(pos.pnl)}
            </span>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-3 text-fg3 font-mono">
          <span className="text-[10px] font-bold tracking-wider uppercase">No Position</span>
          <span className="text-[9px] mt-0.5">0.0000 XAU</span>
        </div>
      )}
    </div>
  );
});
