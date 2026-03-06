// file: frontend/src/services/api.ts
const BASE = '/api/v1';
const FETCH_TIMEOUT_MS = 15000;

function withTimeout(ms: number): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), ms);
  return controller.signal;
}

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { signal: withTimeout(FETCH_TIMEOUT_MS) });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: withTimeout(FETCH_TIMEOUT_MS),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `API error: ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => fetchJSON<any>('/health'),
  prices: () => fetchJSON<any>('/prices'),
  spreads: (symbol: string, options?: { limit?: number; minutes?: number }) => {
    const params = new URLSearchParams({ symbol });
    if (options?.minutes != null) {
      params.set('minutes', String(options.minutes));
    } else {
      params.set('limit', String(options?.limit ?? 500));
    }
    return fetchJSON<any>(`/spreads?${params}`);
  },
  funding: () => fetchJSON<any>('/funding'),
  alerts: (limit = 50) => fetchJSON<any>(`/alerts?limit=${limit}`),
  config: () => fetchJSON<any>('/config'),

  // CSV export URL (for direct download)
  exportCsvUrl: (symbol: string, minutes = 60) =>
    `${BASE}/spreads/export?symbol=${symbol}&minutes=${minutes}`,

  portfolio: () => fetchJSON<any>('/portfolio'),
  positions: (symbol: string) => fetchJSON<any>(`/positions?symbol=${symbol}`),

  executeArb: (symbol: string, side: 'LONG_LIGHTER' | 'SHORT_LIGHTER', amount: number) =>
    postJSON<any>('/execute', { symbol, side, amount }),

  closePositions: (symbol: string) =>
    postJSON<any>('/execute/close_all', { symbol }),
};
