import { getApiKey } from './api';
import type { RiskAuditResponse, RiskConfigPatch, RiskConfigResponse, RiskStatus } from '../types/risk';

const BASE = '/api/v1/risk';
const FETCH_TIMEOUT_MS = 15000;

function withTimeout(ms: number): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), ms);
  return controller.signal;
}

function authHeaders(): Record<string, string> {
  const key = getApiKey();
  return key ? { 'X-API-Key': key } : {};
}

async function requestJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    signal: withTimeout(FETCH_TIMEOUT_MS),
    headers: {
      ...(options?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : `API error: ${response.status}`);
  }
  return response.json();
}

export const riskApi = {
  hasApiKey: () => Boolean(getApiKey()),
  status: () => requestJSON<RiskStatus>('/status'),
  config: () => requestJSON<RiskConfigResponse>('/config'),
  updateConfig: (patch: RiskConfigPatch) =>
    requestJSON<{ status: string; config: RiskConfigResponse['config'] }>('/config', {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(patch),
    }),
  activateKillSwitch: (reason: string) =>
    requestJSON<{ active: boolean; reason: string; activation_ts: number }>('/kill-switch/activate', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ reason }),
    }),
  resetKillSwitch: () =>
    requestJSON<{ active: boolean; reason: string; activation_ts: number }>('/kill-switch/reset', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({}),
    }),
  audit: (params?: { page?: number; page_size?: number; decision_type?: string; symbol?: string }) => {
    const search = new URLSearchParams({
      page: String(params?.page ?? 1),
      page_size: String(params?.page_size ?? 25),
    });
    if (params?.decision_type) search.set('decision_type', params.decision_type);
    if (params?.symbol) search.set('symbol', params.symbol);
    return requestJSON<RiskAuditResponse>(`/audit?${search}`, {
      headers: authHeaders(),
    });
  },
};
