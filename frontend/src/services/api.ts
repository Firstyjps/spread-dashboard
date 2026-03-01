// file: frontend/src/services/api.ts
import axios from 'axios';
const BASE = '/api/v1';
const BASE_URL = 'http://localhost:8000/api/v1';

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
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

  executeArb: async (symbol: string, side: 'LONG_LIGHTER' | 'SHORT_LIGHTER', amount: number) => {
    const response = await axios.post(`${BASE_URL}/execute`, {
      symbol,
      side,
      amount
    });
    return response.data;
  },

  closePositions: async (symbol: string) => {
    const response = await fetch(`${BASE_URL}/execute/close_all`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ symbol }), 
    });
    
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Network response was not ok');
    }
    return response.json();
  }
};
