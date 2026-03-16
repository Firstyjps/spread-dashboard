// file: frontend/src/components/health/HealthPage.tsx
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';

export function HealthPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 5000,
  });

  const [reloading, setReloading] = useState(false);
  const [reloadMsg, setReloadMsg] = useState('');

  const handleReloadConfig = async () => {
    setReloading(true);
    setReloadMsg('');
    try {
      const res = await api.reloadConfig();
      setReloadMsg(res.key_changed ? 'Config reloaded — API key changed' : 'Config reloaded — no key change');
    } catch (e) {
      setReloadMsg(`Reload failed: ${e}`);
    } finally {
      setReloading(false);
    }
  };

  if (isLoading) {
    return <div className="text-gray-500">Checking health...</div>;
  }

  if (error) {
    return (
      <div className="bg-red-900/30 text-red-300 p-4 rounded">
        Failed to reach backend: {String(error)}
      </div>
    );
  }

  const bybit = data?.exchanges?.bybit;
  const lighter = data?.exchanges?.lighter;

  return (
    <div className="space-y-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase">System Health</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Bybit */}
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <div className="flex items-center gap-2 mb-3">
            <span
              className={`w-3 h-3 rounded-full ${
                bybit?.status === 'ok' ? 'bg-emerald-400' : 'bg-red-400'
              }`}
            />
            <h3 className="font-semibold">Bybit</h3>
          </div>
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-400">Status</dt>
              <dd className="font-mono">{bybit?.status ?? 'unknown'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-400">Latency</dt>
              <dd className="font-mono">{bybit?.latency_ms ?? '-'} ms</dd>
            </div>
            {bybit?.error && (
              <div className="flex justify-between">
                <dt className="text-gray-400">Error</dt>
                <dd className="font-mono text-red-400">{bybit.error}</dd>
              </div>
            )}
          </dl>
        </div>

        {/* Lighter */}
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <div className="flex items-center gap-2 mb-3">
            <span
              className={`w-3 h-3 rounded-full ${
                lighter?.status === 'ok' ? 'bg-emerald-400' : 'bg-red-400'
              }`}
            />
            <h3 className="font-semibold">Lighter</h3>
          </div>
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-400">Status</dt>
              <dd className="font-mono">{lighter?.status ?? 'unknown'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-400">Latency</dt>
              <dd className="font-mono">{lighter?.latency_ms ?? '-'} ms</dd>
            </div>
            {lighter?.error && (
              <div className="flex justify-between">
                <dt className="text-gray-400">Error</dt>
                <dd className="font-mono text-red-400">{lighter.error}</dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      {/* Symbols */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase mb-2">Tracked Symbols</h3>
        <div className="flex gap-2">
          {data?.symbols?.map((s: string) => (
            <span key={s} className="px-3 py-1 bg-gray-800 rounded font-mono text-sm">
              {s}
            </span>
          ))}
        </div>
      </section>

      {/* Config Reload */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase mb-2">Configuration</h3>
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <div className="flex items-center gap-4">
            <button
              onClick={handleReloadConfig}
              disabled={reloading}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded transition-colors"
            >
              {reloading ? 'Reloading...' : 'Reload .env Config'}
            </button>
            <span className="text-sm text-gray-400">
              Re-read .env and recreate API clients without restarting
            </span>
          </div>
          {reloadMsg && (
            <p className={`mt-2 text-sm font-mono ${reloadMsg.includes('failed') ? 'text-red-400' : 'text-emerald-400'}`}>
              {reloadMsg}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
