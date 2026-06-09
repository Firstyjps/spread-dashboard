import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine 
} from 'recharts';
import { RefreshCw, Coins } from 'lucide-react';

function formatDateShort(ts: number) {
  const d = new Date(ts);
  const m = d.toLocaleString('en-US', { month: 'short' });
  const day = d.getDate().toString().padStart(2, '0');
  const h = d.getHours().toString().padStart(2, '0');
  const min = d.getMinutes().toString().padStart(2, '0');
  return `${m} ${day} ${h}:${min}`;
}

export function FundingPage() {
  const [activeSymbol, setActiveSymbol] = useState<string>('XAUTUSDT');
  const [viewMode, setViewMode] = useState<'normal' | 'apr'>('apr');
  const [historyLimit, setHistoryLimit] = useState<number>(288); // Default to ~3 days if 15m intervals

  // Fetch live funding
  const { data: liveData } = useQuery({
    queryKey: ['funding_live'],
    queryFn: () => api.funding(),
    refetchInterval: 60000,
  });

  // Fetch historical funding
  const { data: historyData, isLoading: isLoadingHistory, refetch: refetchHistory } = useQuery({
    queryKey: ['funding_history', activeSymbol, historyLimit],
    queryFn: () => api.fundingHistory(activeSymbol, historyLimit),
    refetchInterval: 5 * 60 * 1000,
  });

  // Fetch current spread/price data
  const { data: spreadData, refetch: refetchSpread } = useQuery({
    queryKey: ['spreads', activeSymbol],
    queryFn: () => api.spreads(activeSymbol),
    refetchInterval: 2000,
  });

  const refetchAll = () => {
    refetchHistory();
    refetchSpread();
  };

  // Calculate live stats
  const currentLive = liveData?.[activeSymbol];
  const liveBybit = currentLive?.bybit?.funding_rate ?? 0;
  const liveLighter = currentLive?.lighter?.funding_rate ?? 0;

  const bAnn = liveBybit * 3 * 365 * 100;
  const lAnn = liveLighter * 24 * 365 * 100;
  const netAnn = lAnn - bAnn;

  const bNorm = liveBybit * 100;
  const lNorm = liveLighter * 100;

  const currentPrice = spreadData?.current?.bybit_mid || 0;
  const dailyNetRatio = (liveLighter * 24) - (liveBybit * 3);
  const dailyUsdProfit = currentPrice * dailyNetRatio;

  const formatPercent = (val: number | undefined | null) => {
    if (val == null) return '0.00%';
    return val.toFixed(4) + '%';
  };

  const chartData = (historyData || []).map((item: any) => {
    const b_ann = (item.bybit_annualized || 0) * 100;
    const l_ann = (item.lighter_annualized || 0) * 100;
    const net_ann = (item.net_funding_annualized || 0) * 100;

    const b_norm = (item.bybit_funding_rate || 0) * 100;
    const l_norm = (item.lighter_funding_rate || 0) * 100;

    return {
      ts: item.ts,
      time: formatDateShort(item.ts),
      bybit: viewMode === 'apr' ? b_ann : b_norm,
      lighter: viewMode === 'apr' ? l_ann : l_norm,
      netEdge: viewMode === 'apr' ? net_ann : (l_norm - b_norm),
    };
  });

  return (
    <div className="p-4 sm:p-6 w-[90%] mx-auto flex-1 flex flex-col min-h-0 space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-black text-fg1 tracking-tight flex items-center gap-2">
            <Coins className="w-6 h-6 text-brand" />
            Funding Tracking
          </h1>
          <p className="text-sm text-fg3 mt-1">Monitor historical and real-time funding rates to optimize arbitrage yields.</p>
        </div>

        <div className="flex items-center gap-2 bg-bg2 p-1.5 rounded-lg border border-border">
          <button
            onClick={() => setViewMode('normal')}
            className={`px-3 py-1.5 text-xs font-bold rounded-md transition-colors ${
              viewMode === 'normal' ? 'bg-bg3 text-fg1 shadow-sm' : 'text-fg3 hover:text-fg2'
            }`}
          >
            NORMAL
          </button>
          <button
            onClick={() => setViewMode('apr')}
            className={`px-3 py-1.5 text-xs font-bold rounded-md transition-colors ${
              viewMode === 'apr' ? 'bg-brand/20 text-brand shadow-sm' : 'text-fg3 hover:text-fg2'
            }`}
          >
            APR
          </button>
        </div>
      </div>

      {/* Live Data Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-bg2 border border-border rounded-xl p-5 flex flex-col">
          <span className="text-xs font-bold text-fg3 uppercase tracking-wider mb-2">Bybit Funding {viewMode === 'apr' ? '(APR)' : '(8h)'}</span>
          <span className={`text-2xl font-black ${bAnn > 0 ? 'text-long' : 'text-short'}`}>
            {formatPercent(viewMode === 'apr' ? bAnn : bNorm)}
          </span>
        </div>
        
        <div className="bg-bg2 border border-border rounded-xl p-5 flex flex-col">
          <span className="text-xs font-bold text-fg3 uppercase tracking-wider mb-2">Lighter Funding {viewMode === 'apr' ? '(APR)' : '(1h)'}</span>
          <span className={`text-2xl font-black ${lAnn > 0 ? 'text-long' : 'text-short'}`}>
            {formatPercent(viewMode === 'apr' ? lAnn : lNorm)}
          </span>
        </div>

        <div className="bg-bg2 border border-border rounded-xl p-5 flex flex-col relative overflow-hidden">
          <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-brand/10 rounded-full blur-2xl"></div>
          <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-bold text-fg3 uppercase tracking-wider">Net Edge {viewMode === 'apr' ? '(APR)' : ''}</span>
          </div>
          <span className={`text-3xl font-black ${netAnn > 0 ? 'text-long' : 'text-short'}`}>
            {formatPercent(viewMode === 'apr' ? netAnn : (lNorm - bNorm))}
          </span>
          <span className="text-xs text-fg3 mt-2 font-medium">
            Daily Est: <span className={dailyUsdProfit > 0 ? 'text-long' : 'text-short'}>{dailyUsdProfit > 0 ? '+' : ''}${dailyUsdProfit.toFixed(4)}</span> / 1 {activeSymbol.replace('USDT', '')}
          </span>
        </div>
      </div>

      {/* Chart Section */}
      <div className="bg-bg2 border border-border rounded-xl p-4 sm:p-6 flex-1 flex flex-col min-h-[400px]">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-lg font-bold text-fg1">Historical Funding Rates</h2>
          
          <div className="flex items-center gap-2">
            <select 
              value={activeSymbol}
              onChange={(e) => setActiveSymbol(e.target.value)}
              className="bg-bg1 border border-border text-fg1 text-sm rounded-md px-3 py-1.5 focus:ring-1 focus:ring-brand focus:border-brand"
            >
              {(liveData ? Object.keys(liveData) : ['XAUTUSDT', 'BTCUSDT', 'ETHUSDT']).map(sym => (
                <option key={sym} value={sym}>{sym}</option>
              ))}
            </select>
            
            <button onClick={() => refetchAll()} className="p-1.5 text-fg3 hover:text-brand bg-bg1 border border-border rounded-md transition-colors">
              <RefreshCw className={`w-4 h-4 ${isLoadingHistory ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        <div className="flex-1 w-full relative min-h-0">
          {isLoadingHistory && chartData.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center text-fg3 animate-pulse z-10 bg-bg2">
              Loading historical data...
            </div>
          ) : chartData.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center text-fg3 z-10 bg-bg2">
              No historical data available. The background loop might just be starting!
            </div>
          ) : null}
          
          <div className="absolute inset-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2B2B36" vertical={false} />
                <XAxis 
                  dataKey="time" 
                  stroke="#5A5A6C" 
                  tick={{ fill: '#8F8F9F', fontSize: 11 }} 
                  tickMargin={10} 
                  minTickGap={30}
                />
                <YAxis 
                  stroke="#5A5A6C" 
                  tick={{ fill: '#8F8F9F', fontSize: 11 }} 
                  tickFormatter={(val) => `${val.toFixed(2)}%`}
                  domain={['auto', 'auto']}
                  width={60}
                />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1A1A24', border: '1px solid #2B2B36', borderRadius: '8px', color: '#FFF' }}
                  itemStyle={{ fontSize: '13px', fontWeight: 'bold' }}
                  labelStyle={{ color: '#8F8F9F', marginBottom: '8px', fontSize: '12px' }}
                  formatter={(value: any, name: any) => [`${Number(value).toFixed(4)}%`, String(name)]}
                />
                <Legend iconType="circle" wrapperStyle={{ paddingTop: '20px', fontSize: '12px' }} />
                <ReferenceLine y={0} stroke="#5A5A6C" strokeDasharray="3 3" />
                <Line 
                  type="monotone" 
                  dataKey="bybit" 
                  name="Bybit" 
                  stroke="#F7A600" 
                  strokeWidth={2} 
                  dot={false} 
                  activeDot={{ r: 4 }} 
                />
                <Line 
                  type="monotone" 
                  dataKey="lighter" 
                  name="Lighter" 
                  stroke="#A855F7" 
                  strokeWidth={2} 
                  dot={false} 
                  activeDot={{ r: 4 }} 
                />
                <Line 
                  type="monotone" 
                  dataKey="netEdge" 
                  name="Net Edge" 
                  stroke="#10B981" 
                  strokeWidth={3} 
                  dot={false} 
                  activeDot={{ r: 6 }} 
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
