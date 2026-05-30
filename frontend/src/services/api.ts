// file: frontend/src/services/api.ts
const BASE = '/api/v1';
const FETCH_TIMEOUT_MS = 15000;
const EXECUTE_TIMEOUT_MS = 60000;
const KEY_STORAGE = 'spread_api_key';

function withTimeout(ms: number): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), ms);
  return controller.signal;
}

export function getApiKey(): string {
  return (typeof window !== 'undefined' && localStorage.getItem(KEY_STORAGE)) || '';
}

export function setApiKey(key: string): void {
  if (typeof window === 'undefined') return;
  if (key) localStorage.setItem(KEY_STORAGE, key);
  else localStorage.removeItem(KEY_STORAGE);
}

function promptForKey(): string {
  return '';
}

function authHeaders(): Record<string, string> {
  const k = getApiKey();
  return k ? { 'X-API-Key': k } : {};
}

async function fetchJSON<T>(path: string, withAuth = false): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    signal: withTimeout(FETCH_TIMEOUT_MS),
    headers: withAuth ? authHeaders() : {},
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function postJSON<T>(path: string, body: unknown, timeoutMs = FETCH_TIMEOUT_MS): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
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
  spreadsHistory: (symbol: string, days = 90) => {
    const params = new URLSearchParams({ symbol, days: String(days) });
    return fetchJSON<any>(`/spreads/history?${params}`);
  },
  funding: () => fetchJSON<any>('/funding'),
  alerts: (limit = 50) => fetchJSON<any>(`/alerts?limit=${limit}`),
  trades: (symbol?: string, limit = 100) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (symbol) params.set('symbol', symbol);
    return fetchJSON<any>(`/trades?${params}`, true);
  },
  config: () => fetchJSON<any>('/config'),

  exportCsvUrl: (symbol: string, minutes = 60) =>
    `${BASE}/spreads/export?symbol=${symbol}&minutes=${minutes}`,

  portfolio: () => fetchJSON<any>('/portfolio'),
  positions: (symbol: string) => fetchJSON<any>(`/positions?symbol=${symbol}`),

  executeArb: (symbol: string, side: 'LONG_LIGHTER' | 'SHORT_LIGHTER', amount: number) =>
    postJSON<any>('/execute', { symbol, side, amount }, EXECUTE_TIMEOUT_MS),

  closePositions: (symbol: string) =>
    postJSON<any>('/execute/close_all', { symbol }, EXECUTE_TIMEOUT_MS),

  autoHedgeStatus: () => fetchJSON<any>('/auto-hedge/status'),
  autoHedgeStart: (config: { symbol: string; poll_interval_s: number; min_delta: number }) =>
    postJSON<any>('/auto-hedge/start', config),
  autoHedgeStop: () => postJSON<any>('/auto-hedge/stop', {}),

  slTpStatus: () => fetchJSON<any>('/sl-tp/status'),
  slTpStart: (config: { symbol: string; sl_delta: number; tp_delta: number; poll_interval_s?: number }) =>
    postJSON<any>('/sl-tp/start', config),
  slTpStop: () => postJSON<any>('/sl-tp/stop', {}),
  slTpReset: () => postJSON<any>('/sl-tp/reset', {}),

  reloadConfig: () => postJSON<any>('/reload-config', {}),
};
