import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';
import { Activity, BrainCircuit, Play, Settings2, ShieldAlert, Wallet, ListOrdered } from 'lucide-react';

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '-';
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function pnlColor(n: number | null | undefined): string {
  if (n == null) return 'text-gray-500';
  if (n > 0) return 'text-green-400';
  if (n < 0) return 'text-red-400';
  return 'text-gray-400';
}

function sideColor(side: string): string {
  return side === 'LONG' ? 'text-green-400 bg-green-900/40' : 'text-red-400 bg-red-900/40';
}

export function AIPage() {
  const queryClient = useQueryClient();
  const [tradeSize, setTradeSize] = useState<string>('10');
  const [threshold, setThreshold] = useState<string>('12');

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['aiStatus'],
    queryFn: async () => {
      // Mock data for previewing without backend
      return {
        status: "running",
        is_dry_run: true,
        trade_size_usd: 50.0,
        max_open_trades: 1,
        profit_threshold_bps: 12.0,
        active_trades: 0,
        last_predicted_bps: 14.7
      };
    },
    refetchInterval: 1000,
  });

  const { data: portfolio } = useQuery({
    queryKey: ['portfolio', 'ai'],
    queryFn: () => api.portfolio('ai'),
    refetchInterval: 5000
  });

  const configMutation = useMutation({
    mutationFn: api.aiConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['aiStatus'] });
    },
  });

  const handleToggleDryRun = () => {
    if (status) {
      configMutation.mutate({ is_dry_run: !status.is_dry_run });
    }
  };

  const handleSaveConfig = () => {
    configMutation.mutate({
      trade_size_usd: parseFloat(tradeSize),
      profit_threshold_bps: parseFloat(threshold),
    });
    alert("Saved AI Configurations!");
  };

  if (statusLoading) {
    return <div className="p-6 text-gray-500 flex items-center gap-2"><Activity className="animate-spin" size={16}/> Loading AI Status...</div>;
  }

  const totals = portfolio?.totals;
  const allPositions = portfolio?.snapshots?.flatMap((s: any) => s.positions) || [];

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <BrainCircuit className="text-purple-500" size={32} />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI Auto-Trade</h1>
          <p className="text-sm text-gray-400">Dynamic XGBoost Regression Model</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Status Card */}
        <div className="bg-bg1 border border-bd1 rounded-lg p-5 flex flex-col gap-4">
          <h2 className="font-semibold flex items-center gap-2"><Activity size={18}/> Live Metrics</h2>
          <div className="bg-bg2 rounded p-4 flex flex-col items-center justify-center gap-2 border border-bd2">
            <span className="text-xs text-gray-400 uppercase tracking-widest">Predicted Profit (Next 2h)</span>
            <span className={`text-4xl font-mono font-bold ${(status?.last_predicted_bps ?? 0) >= (status?.profit_threshold_bps ?? 0) ? 'text-green-500' : 'text-gray-200'}`}>
              {status?.last_predicted_bps?.toFixed(2) || '0.00'} bps
            </span>
          </div>
          <div className="flex justify-between items-center text-sm">
            <span className="text-gray-400">Daemon Status</span>
            <span className="text-green-400 flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span> Running</span>
          </div>
          <div className="flex justify-between items-center text-sm">
            <span className="text-gray-400">Active AI Trades</span>
            <span className="text-white font-mono">{status?.active_trades} / {status?.max_open_trades}</span>
          </div>
        </div>

        {/* Controls Card */}
        <div className="bg-bg1 border border-bd1 rounded-lg p-5 flex flex-col gap-4">
          <h2 className="font-semibold flex items-center gap-2"><Settings2 size={18}/> Controls & Parameters</h2>
          
          {/* Dry Run Toggle */}
          <div className="flex items-center justify-between p-3 rounded bg-bg2 border border-bd1">
            <div className="flex items-center gap-2">
              <ShieldAlert size={18} className={status?.is_dry_run ? "text-yellow-500" : "text-red-500"} />
              <div>
                <div className="text-sm font-medium">Safety Mode (Dry Run)</div>
                <div className="text-[11px] text-gray-500">If ON, AI only sends Telegram alerts. If OFF, uses real money.</div>
              </div>
            </div>
            <button 
              onClick={handleToggleDryRun}
              className={`px-3 py-1 text-xs rounded font-bold ${status?.is_dry_run ? 'bg-yellow-500/20 text-yellow-500 border border-yellow-500/50' : 'bg-red-500/20 text-red-500 border border-red-500/50'}`}
            >
              {status?.is_dry_run ? 'ON (Simulated)' : 'OFF (Live Trading)'}
            </button>
          </div>

          <div className="space-y-3 pt-2">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Trade Size (USD)</label>
              <input 
                type="number" 
                defaultValue={status?.trade_size_usd}
                onChange={e => setTradeSize(e.target.value)}
                className="w-full bg-bg1 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Execution Threshold (bps)</label>
              <input 
                type="number" 
                defaultValue={status?.profit_threshold_bps}
                onChange={e => setThreshold(e.target.value)}
                className="w-full bg-bg1 border border-bd2 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
              />
              <p className="text-[10px] text-gray-500 mt-1">Recommended: &gt; 10 bps (to cover 7.2 bps fee + spread cost)</p>
            </div>
            <button 
              onClick={handleSaveConfig}
              disabled={configMutation.isPending}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded py-2 text-sm font-semibold transition-colors flex items-center justify-center gap-2"
            >
              <Play size={14}/> Save Parameters
            </button>
          </div>
        </div>
      </div>

      {/* Account & Portfolio Summary */}
      <div className="bg-bg1 border border-bd1 rounded-lg p-5 flex flex-col gap-4">
        <h2 className="font-semibold flex items-center gap-2"><Wallet size={18}/> Account Balance</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-bg2 rounded p-3 border border-bd2">
            <div className="text-xs text-gray-500 mb-1">Total Equity</div>
            <div className="font-mono text-lg font-bold text-white">${fmt(totals?.total_equity)}</div>
          </div>
          <div className="bg-bg2 rounded p-3 border border-bd2">
            <div className="text-xs text-gray-500 mb-1">Available to Trade</div>
            <div className="font-mono text-lg text-gray-300">${fmt(totals?.available)}</div>
          </div>
          <div className="bg-bg2 rounded p-3 border border-bd2">
            <div className="text-xs text-gray-500 mb-1">Used Margin</div>
            <div className="font-mono text-lg text-gray-300">${fmt(totals?.used_margin)}</div>
          </div>
          <div className="bg-bg2 rounded p-3 border border-bd2">
            <div className="text-xs text-gray-500 mb-1">Unrealized PnL</div>
            <div className={`font-mono text-lg font-bold ${pnlColor(totals?.unrealized_pnl)}`}>
              {(totals?.unrealized_pnl ?? 0) >= 0 ? '+' : ''}${fmt(totals?.unrealized_pnl)}
            </div>
          </div>
        </div>
      </div>

      {/* Current Open Positions */}
      <div className="bg-bg1 border border-bd1 rounded-lg p-5 flex flex-col gap-4">
        <h2 className="font-semibold flex items-center gap-2"><ListOrdered size={18}/> Current Open Positions</h2>
        {allPositions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono text-left">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-bd1">
                  <th className="py-2 pr-3">Symbol</th>
                  <th className="py-2 pr-3">Exchange</th>
                  <th className="py-2 pr-3">Side</th>
                  <th className="py-2 pr-3 text-right">Qty</th>
                  <th className="py-2 pr-3 text-right">Entry</th>
                  <th className="py-2 pr-3 text-right">Mark</th>
                  <th className="py-2 text-right">uPnL</th>
                </tr>
              </thead>
              <tbody>
                {allPositions.map((pos: any, i: number) => (
                  <tr key={i} className="border-b border-bd2/50 hover:bg-bg2/50 transition-colors">
                    <td className="py-2.5 pr-3 text-gray-200">{pos.symbol.replace('USDT', '')}</td>
                    <td className="py-2.5 pr-3 text-gray-500 text-xs uppercase">{pos.exchange}</td>
                    <td className="py-2.5 pr-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${sideColor(pos.side)}`}>
                        {pos.side}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-right text-gray-300">{fmt(pos.qty, 3)}</td>
                    <td className="py-2.5 pr-3 text-right text-gray-400">{fmt(pos.entry_price, 3)}</td>
                    <td className="py-2.5 pr-3 text-right text-gray-400">{fmt(pos.mark_price, 3)}</td>
                    <td className={`py-2.5 text-right font-bold ${pnlColor(pos.unrealized_pnl)}`}>
                      {pos.unrealized_pnl >= 0 ? '+' : ''}${fmt(pos.unrealized_pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
           <div className="flex items-center justify-center py-8 text-gray-500 text-sm bg-bg2 rounded border border-bd2">
             No open positions currently. (Or backend disconnected)
           </div>
        )}
      </div>
    </div>
  );
}
