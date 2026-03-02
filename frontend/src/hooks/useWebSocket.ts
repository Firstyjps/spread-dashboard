// file: frontend/src/hooks/useWebSocket.ts
import { useEffect, useRef, useState, useCallback } from 'react';

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  autoSubscribe?: string[];
}

export function useWebSocket({ url, onMessage, autoSubscribe }: UseWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

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

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        // Auto-subscribe on connection if symbols specified
        if (autoSubscribe && autoSubscribe.length > 0) {
          ws.send(JSON.stringify({ type: 'subscribe', symbols: autoSubscribe }));
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          onMessage?.(data);
        } catch (err) {
          console.warn('[WS] Failed to parse message:', err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        reconnectTimer.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      reconnectTimer.current = setTimeout(connect, 3000);
    }
  }, [url, onMessage, autoSubscribe]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { isConnected, send, subscribe, unsubscribe };
}
