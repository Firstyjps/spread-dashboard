// file: frontend/src/services/api.ts
const BASE = '/api/v1';

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  health: () => fetchJSON<any>('/health'),
  prices: () => fetchJSON<any>('/prices'),
  spreads: (symbol: string, limit = 500) =>
    fetchJSON<any>(`/spreads?symbol=${symbol}&limit=${limit}`),
  funding: () => fetchJSON<any>('/funding'),
  alerts: (limit = 50) => fetchJSON<any>(`/alerts?limit=${limit}`),
  config: () => fetchJSON<any>('/config'),
};
