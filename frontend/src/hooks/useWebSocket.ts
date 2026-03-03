// file: frontend/src/hooks/useWebSocket.ts
import { useEffect, useRef, useState, useCallback } from 'react';

type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  autoSubscribe?: string[];
}

// ─── Reconnect config ──────────────────────────────────────────
const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;
const MAX_RETRIES = 30;
const HEARTBEAT_INTERVAL_MS = 15000;
const HEARTBEAT_TIMEOUT_MS = 5000;

export function useWebSocket({ url, onMessage, autoSubscribe }: UseWebSocketOptions) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const heartbeatTimer = useRef<ReturnType<typeof setInterval>>();
  const pongTimer = useRef<ReturnType<typeof setTimeout>>();
  const retryCount = useRef(0);
  const backoffMs = useRef(INITIAL_BACKOFF_MS);

  // Keep latest onMessage in a ref to avoid reconnect loops
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const autoSubRef = useRef(autoSubscribe);
  autoSubRef.current = autoSubscribe;

  const clearTimers = useCallback(() => {
    clearTimeout(reconnectTimer.current);
    clearInterval(heartbeatTimer.current);
    clearTimeout(pongTimer.current);
  }, []);

  const send = useCallback((data: string | object) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }, []);

  const subscribe = useCallback((symbols: string[]) => {
    send({ type: 'subscribe', symbols });
  }, [send]);

  const unsubscribe = useCallback((symbols: string[]) => {
    send({ type: 'unsubscribe', symbols });
  }, [send]);

  const startHeartbeat = useCallback((ws: WebSocket) => {
    clearInterval(heartbeatTimer.current);
    clearTimeout(pongTimer.current);

    heartbeatTimer.current = setInterval(() => {
      if (ws.readyState !== WebSocket.OPEN) return;

      // Send ping
      ws.send('ping');

      // Wait for pong — if not received in 5s, connection is dead
      pongTimer.current = setTimeout(() => {
        console.warn('[WS] Heartbeat timeout — closing stale connection');
        ws.close();
      }, HEARTBEAT_TIMEOUT_MS);
    }, HEARTBEAT_INTERVAL_MS);
  }, []);

  const connect = useCallback(() => {
    try {
      if (retryCount.current >= MAX_RETRIES) {
        console.error(`[WS] Max retries (${MAX_RETRIES}) reached — giving up`);
        setConnectionState('disconnected');
        return;
      }

      const isReconnect = retryCount.current > 0;
      setConnectionState(isReconnect ? 'reconnecting' : 'connecting');

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnectionState('connected');
        // Reset backoff on successful connect
        retryCount.current = 0;
        backoffMs.current = INITIAL_BACKOFF_MS;

        // Auto-subscribe on connection if symbols specified
        const subs = autoSubRef.current;
        if (subs && subs.length > 0) {
          ws.send(JSON.stringify({ type: 'subscribe', symbols: subs }));
        }

        // Start heartbeat
        startHeartbeat(ws);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Handle pong — clear the timeout
          if (data.type === 'pong') {
            clearTimeout(pongTimer.current);
            return;
          }

          onMessageRef.current?.(data);
        } catch (err) {
          console.warn('[WS] Failed to parse message:', err);
        }
      };

      ws.onclose = () => {
        clearInterval(heartbeatTimer.current);
        clearTimeout(pongTimer.current);
        setConnectionState('reconnecting');

        // Exponential backoff: 1s → 2s → 4s → 8s → ... → max 30s
        const delay = backoffMs.current;
        retryCount.current += 1;
        backoffMs.current = Math.min(backoffMs.current * 2, MAX_BACKOFF_MS);

        reconnectTimer.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      const delay = backoffMs.current;
      retryCount.current += 1;
      backoffMs.current = Math.min(backoffMs.current * 2, MAX_BACKOFF_MS);
      reconnectTimer.current = setTimeout(connect, delay);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, startHeartbeat]);

  useEffect(() => {
    connect();
    return () => {
      clearTimers();
      wsRef.current?.close();
    };
  }, [connect, clearTimers]);

  const isConnected = connectionState === 'connected';

  return { isConnected, connectionState, send, subscribe, unsubscribe };
}
