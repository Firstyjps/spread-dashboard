// file: frontend/src/services/api.ts
const BASE = '/api/v1';
const FETCH_TIMEOUT_MS = 15000;
const EXECUTE_TIMEOUT_MS = 60000; // Execution can take 15s+ (maker engine) + Lighter

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

async function postJSON<T>(path: string, body: unknown, timeoutMs = FETCH_TIMEOUT_MS): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: withTimeout(timeoutMs),
    });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s — backend may still be processing`);
    }
    throw err;
  }
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
    postJSON<any>('/execute', { symbol, side, amount }, EXECUTE_TIMEOUT_MS),

  closePositions: (symbol: string) =>
    postJSON<any>('/execute/close_all', { symbol }, EXECUTE_TIMEOUT_MS),

  // Auto-Hedge
  autoHedgeStatus: () => fetchJSON<any>('/auto-hedge/status'),
  autoHedgeStart: (config: { symbol: string; poll_interval_s: number; min_delta: number }) =>
    postJSON<any>('/auto-hedge/start', config),
  autoHedgeStop: () => postJSON<any>('/auto-hedge/stop', {}),
};
